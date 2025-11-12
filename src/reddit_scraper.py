"""Reddit scraper for the Telegram bot."""

import asyncio
import logging
import os
import subprocess
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests
import praw
from PIL import Image

# Try to import yt-dlp for reliable video downloads
try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False
    yt_dlp = None

logger = logging.getLogger(__name__)


class RedditScraper:
    """Reddit content scraper."""
    
    def __init__(self, client_id: str, client_secret: str, user_agent: str, temp_dir: str, config=None):
        """Initialize the Reddit scraper."""
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.config = config  # Store config for timeout and optimization settings
        
        # Initialize Reddit API client
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )
        
        # Supported media extensions
        self.image_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
        self.video_extensions = {'.mp4', '.webm', '.mov', '.avi', '.gif'}
        
        if not YTDLP_AVAILABLE:
            logger.warning("yt-dlp not installed - video downloads may fail or have no audio")
        else:
            logger.info("yt-dlp is available for reliable video downloads")
        
        # Check for HandBrake
        self.handbrake_path = self._find_handbrake_executable()
        if not self.handbrake_path:
            logger.warning("HandBrake not found in PATH - videos will not be re-encoded for Telegram")
        else:
            logger.info(f"HandBrake found at: {self.handbrake_path}")
        
        logger.info("Reddit scraper initialized")
    
    async def scrape_subreddit(self, subreddit_name: str, sort_type: str = 'hot', 
                              time_filter: str = 'day', limit: int = 25) -> List[Dict[str, Any]]:
        """
        Scrape posts from a subreddit.
        
        Args:
            subreddit_name: Name of the subreddit (without r/)
            sort_type: Sort type (hot, new, top, rising)
            time_filter: Time filter for 'top' sort (hour, day, week, month, year, all)
            limit: Maximum number of posts to fetch
        
        Returns:
            List of post dictionaries containing media posts only
        """
        try:
            # Clean subreddit name
            subreddit_name = subreddit_name.replace('r/', '').replace('/', '')
            
            logger.info(f"Scraping r/{subreddit_name} - {sort_type} ({time_filter}) - limit: {limit}")
            
            subreddit = self.reddit.subreddit(subreddit_name)
            
            # Get posts based on sort type
            if sort_type == 'hot':
                posts = subreddit.hot(limit=limit)
            elif sort_type == 'new':
                posts = subreddit.new(limit=limit)
            elif sort_type == 'top':
                posts = subreddit.top(time_filter=time_filter, limit=limit)
            elif sort_type == 'rising':
                posts = subreddit.rising(limit=limit)
            else:
                logger.warning(f"Unknown sort type: {sort_type}, defaulting to hot")
                posts = subreddit.hot(limit=limit)
            
            media_posts = []
            
            for post in posts:
                # Skip text posts, we only want media
                if not self._has_media(post):
                    continue
                
                media_type = self._get_media_type(post)
                
                post_data = {
                    'id': post.id,
                    'subreddit': subreddit_name,
                    'title': post.title,
                    'url': post.url,
                    'author': str(post.author),
                    'created_utc': int(post.created_utc),
                    'permalink': f"https://reddit.com{post.permalink}",
                    'score': post.score,
                    'num_comments': post.num_comments,
                    'upvote_ratio': post.upvote_ratio,
                    'media_type': media_type,
                    'thumbnail': getattr(post, 'thumbnail', None)
                }
                
                # Store gallery metadata if it's a gallery post
                if media_type == 'gallery':
                    post_data['gallery_data'] = getattr(post, 'gallery_data', None)
                    post_data['media_metadata'] = getattr(post, 'media_metadata', None)
                
                media_posts.append(post_data)
            
            logger.info(f"Found {len(media_posts)} media posts from r/{subreddit_name}")
            return media_posts
            
        except Exception as e:
            logger.error(f"Error scraping r/{subreddit_name}: {e}")
            return []
    
    def _has_media(self, post) -> bool:
        """Check if a post contains media (image or video)."""
        # Check if it's an image or video URL
        if self._is_direct_media_url(post.url):
            return True
        
        # Check for Reddit hosted images/videos
        if hasattr(post, 'is_video') and post.is_video:
            return True
        
        # Check for Reddit gallery
        if hasattr(post, 'is_gallery') and post.is_gallery:
            return True
        
        # Check for media/preview
        if hasattr(post, 'preview') and post.preview:
            return True
        
        # Check common image hosting sites
        media_domains = {
            'i.redd.it', 'i.imgur.com', 'imgur.com', 'gfycat.com', 
            'redgifs.com', 'v.redd.it', 'youtube.com', 'youtu.be'
        }
        
        from urllib.parse import urlparse
        domain = urlparse(post.url).netloc.lower()
        
        return any(domain.endswith(md) for md in media_domains)
    
    def _is_direct_media_url(self, url: str) -> bool:
        """Check if URL is a direct media file."""
        from urllib.parse import urlparse
        path = urlparse(url).path.lower()
        return any(path.endswith(ext) for ext in self.image_extensions | self.video_extensions)
    
    def _get_media_type(self, post) -> str:
        """Determine the type of media in a post using PRAW properties.
        
        Returns:
            'gallery': Reddit gallery posts
            'video': Videos (Reddit native, external, yt-dlp compatible)
            'image': Direct image files or image hosting services
            'text': Text posts or non-media content
        """
        try:
            # Check for Reddit gallery FIRST
            if hasattr(post, 'gallery_data') and post.gallery_data:
                return 'gallery'
            
            # Check for Reddit video
            if hasattr(post, 'media') and post.media:
                if 'reddit_video' in post.media:
                    return 'video'
            
            # Check for direct image file extensions
            image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')
            if post.url.endswith(image_extensions):
                return 'image'
            
            # Check for Reddit's own image CDN
            if 'i.redd.it' in post.url or 'preview.redd.it' in post.url:
                return 'image'
            
            # Check if it's a text/self post (no media to download)
            if post.is_self:
                return 'text'
            
            # For non-self posts with URLs we don't recognize,
            # try yt-dlp (supports YouTube, TikTok, Twitter, Instagram, etc.)
            return 'video'
        
        except Exception as e:
            logger.error(f"Error determining media type: {e}")
            return 'text'
    
    async def download_media(self, post_data: Dict[str, Any]) -> Optional[str]:
        """
        Download media file for a post.
        
        Returns:
            Path to downloaded file or None if download failed
        """
        try:
            url = post_data['url']
            media_type = post_data['media_type']
            post_id = post_data['id']
            
            logger.info(f"Downloading media for post {post_id}: {url}")
            
            # Handle gallery posts - extract actual image URLs from Reddit metadata
            if media_type == 'gallery':
                logger.info(f"Processing Reddit gallery for post {post_id}")
                gallery_data = post_data.get('gallery_data')
                media_metadata = post_data.get('media_metadata')
                
                if gallery_data and media_metadata:
                    gallery_images = self._extract_gallery_images(gallery_data, media_metadata)
                    if gallery_images:
                        logger.info(f"Found {len(gallery_images)} images in gallery, downloading first")
                        # Download first image from gallery
                        first_image_url = gallery_images[0]
                        file_path = await self._download_file(first_image_url, post_id, 'jpg')
                        if file_path:
                            return await self._validate_and_convert_image(file_path)
                    else:
                        logger.warning(f"Could not extract image URLs from gallery metadata")
                        return None
                else:
                    logger.warning(f"Gallery post missing gallery_data or media_metadata")
                    return None
            
            # Use yt-dlp for video downloads and any URL it can handle
            if media_type == 'video':
                if not YTDLP_AVAILABLE:
                    logger.warning(f"yt-dlp not available, cannot process: {url}")
                    return None
                
                logger.info(f"Using yt-dlp to download from {url}")
                # For Reddit videos, use the permalink which yt-dlp can parse
                reddit_url = post_data.get('permalink', url)
                file_path = await self._download_video_with_ytdlp(reddit_url, post_id)
                
                if file_path:
                    logger.info(f"Downloaded media to: {file_path} (size: {Path(file_path).stat().st_size} bytes)")
                    
                    # Encode video for Telegram compatibility if HandBrake is available
                    if self.handbrake_path:
                        encoded_path = await self._encode_video_for_telegram(file_path, post_id)
                        if encoded_path:
                            logger.info(f"Successfully encoded video for Telegram: {encoded_path}")
                            # Clean up original downloaded file
                            try:
                                Path(file_path).unlink()
                            except:
                                pass
                            return encoded_path
                        else:
                            logger.warning(f"Video encoding failed, using original: {file_path}")
                            return file_path
                    else:
                        logger.debug("HandBrake not available, returning video without re-encoding")
                        return file_path
                else:
                    # yt-dlp failed - this URL is likely not downloadable
                    logger.warning(f"yt-dlp could not download from {url}")
                    return None
            
            # For non-video content or if yt-dlp is unavailable, use direct download
            if media_type == 'gif':
                logger.info(f"Processing GIF (direct download): {url}")
                download_url = await self._get_download_url(url, media_type)
                if not download_url:
                    logger.warning(f"Could not get download URL for GIF: {url}")
                    return None
            
            elif media_type == 'gifv':
                logger.info(f"Processing GIFV (converting to video): {url}")
                download_url = await self._get_download_url(url, media_type)
                if not download_url:
                    logger.warning(f"Could not get download URL for GIFV: {url}")
                    return None
            
            else:
                # For all other media types (images, non-Reddit videos)
                download_url = await self._get_download_url(url, media_type)
                if not download_url:
                    logger.warning(f"Could not get download URL for {url}")
                    return None
            
            logger.info(f"Downloading from URL: {download_url}")
            
            # Download the file
            response = requests.get(download_url, stream=True, timeout=30, 
                                  headers={'User-Agent': 'Mozilla/5.0 (compatible; RedditBot/1.0)'})
            response.raise_for_status()
            
            # Determine file extension
            content_type = response.headers.get('content-type', '')
            extension = self._get_extension_from_content_type(content_type, download_url)
            
            # Create temporary file
            file_path = self.temp_dir / f"{post_id}{extension}"
            
            # Save file
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Validate file size
            if file_path.stat().st_size == 0:
                logger.warning(f"Downloaded file is empty: {file_path}")
                file_path.unlink()
                return None
            
            # Validate and potentially convert image
            if media_type == 'image':
                file_path = await self._validate_and_convert_image(file_path)
            
            logger.info(f"Downloaded media to: {file_path} (size: {file_path.stat().st_size} bytes)")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"Error downloading media for post {post_data.get('id', 'unknown')}: {e}")
            return None
    
    async def _get_download_url(self, url: str, media_type: str) -> Optional[str]:
        """Get the actual download URL for different hosting services."""
        # Direct media URLs
        if self._is_direct_media_url(url):
            return url
        
        # Reddit hosted images
        if 'i.redd.it' in url:
            return url
        
        # Reddit hosted videos (v.redd.it) - these need special handling
        if 'v.redd.it' in url:
            # Try to get the DASH video URL
            try:
                # v.redd.it URLs usually have a DASH_720.mp4 or similar format
                if not url.endswith('.mp4'):
                    # Try different quality variants
                    for quality in ['DASH_720.mp4', 'DASH_480.mp4', 'DASH_360.mp4', 'DASH_240.mp4']:
                        test_url = f"{url.rstrip('/')}/{quality}"
                        try:
                            response = requests.head(test_url, timeout=10)
                            if response.status_code == 200:
                                return test_url
                        except:
                            continue
                    
                    # If no DASH version found, try the fallback URL
                    fallback_url = f"{url.rstrip('/')}/DASH_96.mp4"
                    return fallback_url
                return url
            except Exception as e:
                logger.warning(f"Error processing v.redd.it URL {url}: {e}")
                return url
        
        # Imgur
        if 'imgur.com' in url:
            if 'i.imgur.com' not in url:
                # Convert imgur page URL to direct media URL
                imgur_id = url.split('/')[-1].split('.')[0]
                # Try video first, then image
                if media_type == 'video':
                    return f"https://i.imgur.com/{imgur_id}.mp4"
                else:
                    return f"https://i.imgur.com/{imgur_id}.jpg"
            elif url.endswith('.gifv'):
                # Convert .gifv to .mp4 for better compatibility
                return url.replace('.gifv', '.mp4')
            return url
        
        # Gfycat - get the actual MP4 URL
        if 'gfycat.com' in url:
            try:
                gfy_id = url.split('/')[-1]
                # Gfycat direct MP4 URL pattern
                return f"https://giant.gfycat.com/{gfy_id}.mp4"
            except:
                return url
        
        # RedGifs - similar to Gfycat
        if 'redgifs.com' in url:
            try:
                # RedGifs URLs are more complex, for now return as-is
                # This might need API integration for full support
                return url
            except:
                return url
        
        # For other services, return the original URL and let requests handle it
        return url
    
    def _get_extension_from_content_type(self, content_type: str, url: str) -> str:
        """Get file extension from content type or URL."""
        # Try content type first
        content_type_map = {
            'image/jpeg': '.jpg',
            'image/jpg': '.jpg',
            'image/png': '.png',
            'image/webp': '.webp',
            'image/gif': '.gif',
            'video/mp4': '.mp4',
            'video/webm': '.webm',
            'video/quicktime': '.mov'
        }
        
        if content_type in content_type_map:
            return content_type_map[content_type]
        
        # Try URL extension
        from urllib.parse import urlparse
        path = urlparse(url).path
        if '.' in path:
            ext = Path(path).suffix.lower()
            # Convert .gifv to .mp4 for better compatibility
            if ext == '.gifv':
                return '.mp4'
            return ext
        
        # Default
        return '.jpg'
    
    def _extract_gallery_images(self, gallery_data: Dict[str, Any], media_metadata: Dict[str, Any]) -> List[str]:
        """
        Extract actual image URLs from Reddit gallery metadata.
        
        Args:
            gallery_data: Gallery structure from post.gallery_data
            media_metadata: Media metadata from post.media_metadata
        
        Returns:
            List of image URLs from the gallery
        """
        try:
            image_urls = []
            
            # gallery_data contains items with media_id references
            gallery_items = gallery_data.get('items', [])
            
            for item in gallery_items:
                media_id = item.get('media_id')
                if not media_id or media_id not in media_metadata:
                    continue
                
                media_info = media_metadata[media_id]
                media_type = media_info.get('type')
                
                # Only process images, skip videos in galleries
                if media_type == 'image':
                    # Extract image URL - it's in the 's' key under various formats
                    if 's' in media_info and 'u' in media_info['s']:
                        image_url = media_info['s']['u']
                        image_urls.append(image_url)
                        logger.debug(f"Extracted gallery image: {image_url}")
            
            return image_urls
        
        except Exception as e:
            logger.error(f"Error extracting gallery images: {e}")
            return []
    
    async def _download_file(self, url: str, post_id: str, default_ext: str = 'jpg') -> Optional[str]:
        """Download a file from a URL and save to temp directory."""
        try:
            logger.info(f"Downloading file from URL: {url}")
            
            response = requests.get(url, stream=True, timeout=30,
                                  headers={'User-Agent': 'Mozilla/5.0 (compatible; RedditBot/1.0)'})
            response.raise_for_status()
            
            # Determine file extension
            content_type = response.headers.get('content-type', '')
            extension = self._get_extension_from_content_type(content_type, url)
            
            # Create temporary file
            file_path = self.temp_dir / f"{post_id}{extension}"
            
            # Save file
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Validate file size
            if file_path.stat().st_size == 0:
                logger.warning(f"Downloaded file is empty: {file_path}")
                file_path.unlink()
                return None
            
            logger.info(f"Downloaded file to: {file_path} ({file_path.stat().st_size} bytes)")
            return str(file_path)
        
        except Exception as e:
            logger.error(f"Failed to download file from {url}: {e}")
            return None
    
    async def _validate_and_convert_image(self, file_path: Path) -> Path:
        """Validate and potentially convert image to a supported format."""
        try:
            with Image.open(file_path) as img:
                # Check if image is valid
                img.verify()
                
                # Reopen for potential conversion (verify() closes the image)
                with Image.open(file_path) as img:
                    # Convert RGBA to RGB for JPEG compatibility
                    if img.mode in ('RGBA', 'LA'):
                        # Create white background
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'RGBA':
                            background.paste(img, mask=img.split()[-1])  # Use alpha channel as mask
                        else:
                            background.paste(img)
                        img = background
                    
                    # Convert to RGB if needed
                    if img.mode != 'RGB' and file_path.suffix.lower() in ['.jpg', '.jpeg']:
                        img = img.convert('RGB')
                    
                    # Save converted image if needed
                    if img != Image.open(file_path):
                        img.save(file_path, quality=85, optimize=True)
            
            return file_path
            
        except Exception as e:
            logger.warning(f"Image validation/conversion failed for {file_path}: {e}")
            # Return original path even if validation failed
            return file_path
    
    async def _download_video_with_ytdlp(self, url: str, post_id: str) -> Optional[str]:
        """Download video using yt-dlp, which handles audio+video combination automatically."""
        try:
            output_template = str(self.temp_dir / f"{post_id}.%(ext)s")
            
            # Get timeout setting - use longer timeout for video downloads (300s = 5 minutes)
            timeout = getattr(self.config, 'video_timeout_seconds', 300) if self.config else 300
            
            # Find FFmpeg executable - check multiple common locations
            ffmpeg_path = shutil.which('ffmpeg')
            
            # If not found via which, check common installation paths
            if not ffmpeg_path:
                common_paths = [
                    '/usr/bin/ffmpeg',
                    '/usr/local/bin/ffmpeg',
                    '/opt/ffmpeg/bin/ffmpeg',
                    '/home/pi/.local/bin/ffmpeg',
                ]
                for path in common_paths:
                    if Path(path).exists():
                        ffmpeg_path = path
                        logger.info(f"Found FFmpeg at: {path}")
                        break
            
            if ffmpeg_path:
                logger.info(f"Using FFmpeg at: {ffmpeg_path}")
            else:
                logger.warning("FFmpeg not found - videos may download without audio")
            
            # Configure yt-dlp to download best quality available
            # Prefer formats that already have audio+video combined (like mp4)
            # Fallback to best single file if merge not possible
            ydl_opts = {
                'format': 'best[ext=mp4]/best[ext=mkv]/best',
                'outtmpl': output_template,
                'quiet': False,
                'no_warnings': False,
                'prefer_ffmpeg': True,
                'keepvideo': False,
                'socket_timeout': timeout,
                # Add proper headers to handle Reddit's access restrictions
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': '*/*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Sec-Fetch-Dest': 'video',
                    'Sec-Fetch-Mode': 'no-cors',
                    'Sec-Fetch-Site': 'cross-site',
                    'Range': 'bytes=0-',
                },
                # Use IPv4 only (sometimes IPv6 has issues)
                'socket_family': 'AF_INET',
                # Increase retries for stability
                'retries': 10,
            }
            
            # Explicitly set FFmpeg location if found
            if ffmpeg_path:
                ydl_opts['ffmpeg_location'] = ffmpeg_path
                # If we found FFmpeg, allow merging for best quality
                ydl_opts['format'] = 'bestvideo+bestaudio/best[ext=mp4]/best'
            
            logger.info(f"Downloading video with yt-dlp from {url} (timeout: {timeout}s)")
            
            # Ensure system PATH is available for FFmpeg
            import os
            env = os.environ.copy()
            if '/usr/bin' not in env.get('PATH', ''):
                env['PATH'] = '/usr/bin:/usr/local/bin:' + env.get('PATH', '')
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                
                file_path = Path(filename)
                if file_path.exists() and file_path.stat().st_size > 0:
                    logger.info(f"yt-dlp successfully downloaded: {filename} ({file_path.stat().st_size} bytes)")
                    return str(file_path)
                else:
                    logger.warning(f"yt-dlp output file is invalid or empty: {filename}")
                    return None
        
        except yt_dlp.utils.DownloadError as e:
            # URL not supported by yt-dlp or extraction failed
            logger.debug(f"yt-dlp cannot handle URL {url}: {str(e)[:100]}")
            return None
        except Exception as e:
            logger.error(f"yt-dlp download failed for {url}: {type(e).__name__}: {e}")
            import traceback
            logger.debug(f"yt-dlp traceback: {traceback.format_exc()}")
            return None
    
    def _get_video_duration(self, video_path: str) -> Optional[float]:
        """Get video duration in seconds using ffprobe."""
        try:
            result = subprocess.run(
                [
                    'ffprobe',
                    '-v', 'error',
                    '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1:novalidate=1',
                    video_path
                ],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0 and result.stdout.strip():
                duration = float(result.stdout.strip())
                logger.debug(f"Video duration: {duration:.1f} seconds")
                return duration
        except (FileNotFoundError, ValueError, subprocess.TimeoutExpired) as e:
            logger.debug(f"Could not determine video duration: {e}")
        
        return None
    
    async def _encode_video_for_telegram(self, input_path: str, post_id: str) -> Optional[str]:
        """
        Encode video with HandBrake for Telegram compatibility.
        
        Skips encoding for long videos that won't complete in time.
        
        Uses Telegram-optimized settings:
        - H.264 video codec
        - AAC audio codec
        - Proper bitrates and resolution
        - Web optimization for thumbnail generation and aspect ratio
        """
        if not self.handbrake_path:
            logger.warning("HandBrake not available, skipping encoding")
            return None
        
        try:
            input_file = Path(input_path)
            
            # Check video duration to avoid long encoding times
            duration = self._get_video_duration(str(input_file))
            
            # Raspberry Pi: skip encoding for videos longer than 2 minutes (120s)
            # Regular systems: skip for videos longer than 10 minutes (600s)
            if self.config and getattr(self.config, 'raspberry_pi_mode', False):
                max_duration = 120  # 2 minutes
            else:
                max_duration = 600  # 10 minutes
            
            if duration and duration > max_duration:
                logger.info(
                    f"Video {post_id} is {duration:.0f}s long (max {max_duration}s for this system). "
                    f"Skipping encoding to stay within 5-minute processing window."
                )
                return None  # Return None to use original yt-dlp file
            
            output_file = self.temp_dir / f"{post_id}_encoded.mp4"
            
            logger.info(f"Encoding video for Telegram: {input_file} -> {output_file}")
            
            # HandBrake CLI command for Telegram-optimized encoding
            cmd = [
                self.handbrake_path,
                '-i', str(input_file),
                '-o', str(output_file),
                '-e', 'x264',  # H.264 encoder
                '-q', '22',  # Quality level (18-28, lower is better)
                '-a', '1',  # Audio track 1
                '-E', 'aac',  # AAC audio codec
                '-B', '128',  # Audio bitrate (128kbps)
                '--loose-anamorphic',  # Preserve aspect ratio
                '--optimize',  # Web optimized MP4 (fixes thumbnail and aspect ratio)
            ]
            
            # Add Raspberry Pi optimizations if enabled
            if self.config and getattr(self.config, 'raspberry_pi_mode', False):
                logger.info("Using Raspberry Pi optimized settings")
                cmd.extend([
                    '-q', '24',  # Slightly lower quality for faster encoding
                ])
            
            # Use 5-minute timeout for encoding
            timeout = 300
            
            logger.debug(f"Running HandBrake with {timeout}s timeout: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0 and output_file.exists() and output_file.stat().st_size > 0:
                logger.info(f"Video encoding successful: {output_file} ({output_file.stat().st_size} bytes)")
                return str(output_file)
            else:
                logger.error(f"HandBrake encoding failed with return code {result.returncode}")
                if result.stderr:
                    logger.error(f"HandBrake stderr: {result.stderr[:500]}")
                # Clean up incomplete output file
                if output_file.exists():
                    output_file.unlink()
                return None
        
        except subprocess.TimeoutExpired:
            logger.error(f"HandBrake encoding timed out after {timeout} seconds - video too long or system too slow")
            return None
        except FileNotFoundError:
            logger.error(f"HandBrake executable not found at: {self.handbrake_path}")
            return None
        except Exception as e:
            logger.error(f"Video encoding failed: {e}")
            return None
    
    async def _get_reddit_video_url(self, post_id: str) -> Optional[str]:
        """Get Reddit video URL - now primarily used with yt-dlp."""
        try:
            submission = self.reddit.submission(id=post_id)
            # Return submission URL which yt-dlp can handle
            return submission.url
        except Exception as e:
            logger.error(f"Error getting Reddit video URL for post {post_id}: {e}")
            return None
    
    def cleanup_temp_files(self, max_age_hours: int = 24):
        """Clean up old temporary files."""
        try:
            import time
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            
            for file_path in self.temp_dir.iterdir():
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > max_age_seconds:
                        file_path.unlink()
                        logger.debug(f"Cleaned up old temp file: {file_path}")
                        
        except Exception as e:
            logger.error(f"Error cleaning up temp files: {e}")
    
    def _find_handbrake_executable(self) -> Optional[str]:
        """Find the HandBrake CLI executable in the system."""
        # Try common locations
        possible_paths = [
            'HandBrakeCLI',  # In PATH
            'handbrakecli',  # Linux lowercase
            '/usr/bin/HandBrakeCLI',  # Linux
            '/usr/local/bin/HandBrakeCLI',  # macOS
            '/opt/homebrew/bin/HandBrakeCLI',  # Apple Silicon macOS
            'C:\\Program Files\\HandBrake\\HandBrakeCLI.exe',  # Windows
            'C:\\Program Files (x86)\\HandBrake\\HandBrakeCLI.exe',  # Windows 32-bit
        ]
        
        for path in possible_paths:
            if shutil.which(path):
                logger.info(f"Found HandBrake at: {path}")
                return path
        
        return None
