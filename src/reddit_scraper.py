"""Reddit scraper for the Telegram bot."""

import asyncio
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests
import praw
from PIL import Image
import ffmpeg

logger = logging.getLogger(__name__)


class RedditScraper:
    """Reddit content scraper."""
    
    def __init__(self, client_id: str, client_secret: str, user_agent: str, temp_dir: str):
        """Initialize the Reddit scraper."""
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize Reddit API client
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )
        
        # Supported media extensions
        self.image_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
        self.video_extensions = {'.mp4', '.webm', '.mov', '.avi', '.gif'}
        
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
                    'media_type': self._get_media_type(post),
                    'thumbnail': getattr(post, 'thumbnail', None)
                }
                
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
        """Determine the media type of a post."""
        # Check for video indicators first
        if hasattr(post, 'is_video') and post.is_video:
            return 'video'
        
        # Check for Reddit video
        if hasattr(post, 'media') and post.media and 'reddit_video' in str(post.media):
            return 'video'
        
        # Check URL extension for video files (including GIFs)
        from urllib.parse import urlparse
        path = urlparse(post.url).path.lower()
        
        # GIFs should be treated as videos for Telegram
        if path.endswith('.gif'):
            return 'video'
        
        if any(path.endswith(ext) for ext in self.video_extensions):
            return 'video'
        elif any(path.endswith(ext) for ext in self.image_extensions):
            return 'image'
        
        # Check URL for video hosting sites
        url_lower = post.url.lower()
        if 'v.redd.it' in url_lower:
            return 'video'
        elif 'gfycat.com' in url_lower:
            return 'video'
        elif 'redgifs.com' in url_lower:
            return 'video'
        elif 'streamable.com' in url_lower:
            return 'video'
        # Skip YouTube and other external video sites for now
        # elif 'youtube.com' in url_lower or 'youtu.be' in url_lower:
        #     return 'video'
        
        # For Imgur, check if it might be a video
        if 'imgur.com' in url_lower:
            # Imgur can host both images and videos
            # We'll try to determine this during download
            return 'image'  # Default to image, will be corrected during download if needed
        
        # Default to image for unknown types that have media
        return 'image'
    
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
            
            # For Reddit videos, we need to get the actual video URL from the post
            if media_type == 'video' and 'v.redd.it' in url:
                logger.info(f"Processing Reddit video for post {post_id}")
                video_result = await self._get_reddit_video_url(post_id)
                if video_result:
                    # Check if the result is a local file path (already downloaded and processed)
                    if video_result.startswith('/') or video_result.startswith(str(self.temp_dir)):
                        # It's already a local file, validate it exists and has content
                        if os.path.exists(video_result) and os.path.getsize(video_result) > 0:
                            logger.info(f"Using pre-processed Reddit video: {video_result}")
                            return video_result
                        else:
                            logger.warning(f"Pre-processed video file is invalid: {video_result}")
                            return None
                    else:
                        # It's a URL, use it for standard download
                        logger.info(f"Using Reddit video URL for download: {video_result}")
                        url = video_result
                else:
                    logger.error(f"Failed to get Reddit video URL for post {post_id}")
                    return None
            
            # Handle different URL types
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
            return Path(path).suffix.lower()
        
        # Default
        return '.jpg'
    
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
    
    async def _get_reddit_video_url(self, post_id: str) -> Optional[str]:
        """Get the direct video URL for a Reddit-hosted video with clear fallback strategy."""
        try:
            # Fetch the post again to get complete media data
            submission = self.reddit.submission(id=post_id)
            
            # Strategy 1: Try to get video with audio combination
            if hasattr(submission, 'media') and submission.media:
                reddit_video = submission.media.get('reddit_video')
                if reddit_video:
                    fallback_url = reddit_video.get('fallback_url')
                    if fallback_url:
                        logger.info(f"Found Reddit video fallback URL: {fallback_url}")
                        
                        # Try to download and combine with audio (this may fail, that's OK)
                        try:
                            combined_path = await self._download_and_combine_reddit_video(post_id, fallback_url)
                            if combined_path and os.path.exists(combined_path):
                                logger.info(f"Video processing successful: {combined_path}")
                                return combined_path
                            else:
                                logger.warning(f"Video processing returned empty result, using fallback URL")
                        except Exception as e:
                            logger.info(f"Video processing failed: {e}, using fallback URL")
                        
                        # Fallback: Return the video-only URL for standard download
                        logger.info(f"Using video-only URL: {fallback_url}")
                        return fallback_url
            
            # Strategy 2: Try to construct DASH URLs from submission URL
            if hasattr(submission, 'is_video') and submission.is_video and 'v.redd.it' in submission.url:
                base_url = submission.url.rstrip('/')
                
                # Try different quality options
                for quality in ['DASH_720.mp4', 'DASH_480.mp4', 'DASH_360.mp4', 'DASH_240.mp4']:
                    test_url = f"{base_url}/{quality}"
                    try:
                        response = requests.head(test_url, timeout=5)
                        if response.status_code == 200:
                            logger.info(f"Found Reddit video at quality {quality}: {test_url}")
                            return test_url
                    except:
                        continue
                        
                # Last resort: try the base URL with a generic quality
                fallback_url = f"{base_url}/DASH_720.mp4"
                logger.info(f"Using constructed fallback URL: {fallback_url}")
                return fallback_url
            
            logger.warning(f"Could not find video URL for Reddit post {post_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting Reddit video URL for post {post_id}: {e}")
            return None
    
    async def _download_and_combine_reddit_video(self, post_id: str, video_url: str) -> Optional[str]:
        """Download and combine Reddit video and audio streams with robust fallback inspired by yt-dlp."""
        video_temp = None
        audio_temp = None
        output_temp = None
        
        try:
            # Extract base URL and construct potential audio URLs
            base_url = video_url.split('/DASH_')[0]
            
            # Try multiple audio URL patterns (Reddit can use different formats)
            audio_urls = [
                f"{base_url}/DASH_audio.mp4",
                f"{base_url}/DASH_AUDIO_128.mp4",  # Alternative format
                f"{base_url}/audio",  # Simple fallback
            ]
            
            # Create temporary file paths
            video_temp = self.temp_dir / f"{post_id}_video.mp4"
            audio_temp = self.temp_dir / f"{post_id}_audio.mp4"
            output_temp = self.temp_dir / f"{post_id}.mp4"
            
            logger.info(f"Attempting video+audio combination for post {post_id}")
            
            # Step 1: Download video stream (REQUIRED)
            logger.info(f"Downloading video stream: {video_url}")
            video_response = requests.get(video_url, stream=True, timeout=60,  # Increased from 30
                                        headers={
                                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                                            'Accept': '*/*',
                                            'Accept-Encoding': 'identity'  # Disable compression for better reliability
                                        })
            video_response.raise_for_status()
            
            with open(video_temp, 'wb') as f:
                for chunk in video_response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Verify video was downloaded and has reasonable size
            if not video_temp.exists() or video_temp.stat().st_size < 1024:  # At least 1KB
                logger.error("Video download failed - file is empty or too small")
                return None
            
            logger.info(f"Video downloaded: {video_temp.stat().st_size} bytes")
            
            # Step 2: Try to download audio stream from multiple URLs
            audio_downloaded = False
            audio_url_used = None
            
            for audio_url in audio_urls:
                try:
                    logger.debug(f"Trying audio URL: {audio_url}")
                    audio_response = requests.get(audio_url, stream=True, timeout=30,  # Increased from 15
                                                headers={
                                                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                                                    'Accept': '*/*',
                                                    'Accept-Encoding': 'identity'
                                                })
                    
                    if audio_response.status_code == 200:
                        # Check content-type to ensure it's actually audio
                        content_type = audio_response.headers.get('content-type', '').lower()
                        if 'audio' in content_type or 'video' in content_type:  # video/mp4 can contain audio
                            with open(audio_temp, 'wb') as f:
                                for chunk in audio_response.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            
                            # Verify audio was downloaded and has reasonable size
                            if audio_temp.exists() and audio_temp.stat().st_size > 1024:  # At least 1KB
                                audio_downloaded = True
                                audio_url_used = audio_url
                                logger.info(f"Audio downloaded from {audio_url}: {audio_temp.stat().st_size} bytes")
                                break
                            else:
                                logger.debug(f"Audio file from {audio_url} too small, trying next")
                        else:
                            logger.debug(f"Invalid content-type from {audio_url}: {content_type}")
                    else:
                        logger.debug(f"Audio not available from {audio_url} (HTTP {audio_response.status_code})")
                        
                except Exception as audio_error:
                    logger.debug(f"Audio download failed from {audio_url}: {audio_error}")
                    continue
            
            # Step 3: Combine video+audio if both available
            if audio_downloaded:
                try:
                    logger.info(f"Combining video and audio with ffmpeg (audio from: {audio_url_used})")
                    
                    # Use more robust ffmpeg command inspired by yt-dlp
                    video_input = ffmpeg.input(str(video_temp))
                    audio_input = ffmpeg.input(str(audio_temp))
                    
                    # First try: simple copy (fastest)
                    output = ffmpeg.output(
                        video_input, audio_input, str(output_temp),
                        vcodec='copy', 
                        acodec='copy',  # Try copy first
                        map_metadata=0,  # Copy metadata from first input
                        movflags='faststart'  # Optimize for streaming
                    )
                    
                    # Run ffmpeg with error capture
                    try:
                        ffmpeg.run(output, overwrite_output=True, quiet=True, capture_stdout=True, capture_stderr=True)
                    except ffmpeg.Error as e:
                        # If copy fails, try re-encoding audio
                        logger.warning("Copy mode failed, trying audio re-encoding")
                        output = ffmpeg.output(
                            video_input, audio_input, str(output_temp),
                            vcodec='copy',
                            acodec='aac',  # Re-encode audio to AAC
                            audio_bitrate='128k',
                            map_metadata=0,
                            movflags='faststart'
                        )
                        ffmpeg.run(output, overwrite_output=True, quiet=True, capture_stdout=True, capture_stderr=True)
                    
                    # Verify combined output
                    if output_temp.exists() and output_temp.stat().st_size > video_temp.stat().st_size * 0.8:
                        # Combined file should be at least 80% of video size (reasonable check)
                        logger.info(f"Video+audio combined successfully: {output_temp.stat().st_size} bytes")
                        
                        # Clean up temporary files
                        video_temp.unlink(missing_ok=True)
                        audio_temp.unlink(missing_ok=True)
                        
                        return str(output_temp)
                    else:
                        logger.warning("ffmpeg output is too small or empty, falling back to video-only")
                        if output_temp.exists():
                            output_temp.unlink(missing_ok=True)
                        
                except Exception as ffmpeg_error:
                    logger.warning(f"ffmpeg combination failed: {ffmpeg_error}")
                    if output_temp.exists():
                        output_temp.unlink(missing_ok=True)
            
            # Step 4: Fallback to video-only
            logger.info("Using video-only (no audio or combination failed)")
            
            # Move video file to final output name
            if video_temp and video_temp.exists() and video_temp.stat().st_size > 0:
                try:
                    # Ensure output file doesn't already exist
                    if output_temp.exists():
                        output_temp.unlink()
                    
                    video_temp.rename(output_temp)
                    logger.info(f"Video-only file ready: {output_temp.stat().st_size} bytes")
                    
                    # Clean up audio file if it exists
                    if audio_temp and audio_temp.exists():
                        audio_temp.unlink(missing_ok=True)
                    
                    return str(output_temp)
                except Exception as move_error:
                    logger.warning(f"Failed to move video file: {move_error}")
                    # Last resort: return the video temp file directly
                    if video_temp.exists() and video_temp.stat().st_size > 0:
                        logger.info(f"Using temp video file directly: {video_temp}")
                        return str(video_temp)
            
            logger.error("No valid video file available for fallback")
            return None
            
        except Exception as e:
            logger.error(f"Critical error in video processing for post {post_id}: {e}")
            return None
            
        finally:
            # Emergency cleanup - ensure no temp files are left behind
            for temp_file in [video_temp, audio_temp]:
                try:
                    if temp_file and temp_file.exists() and temp_file != output_temp:
                        temp_file.unlink(missing_ok=True)
                except:
                    pass
    
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
