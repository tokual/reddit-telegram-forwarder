#!/usr/bin/env python3
"""
Raspberry Pi Audio Debug Script
Tests FFmpeg audio combination functionality specifically
"""

import subprocess
import os
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_ffmpeg_audio_combination():
    """Test FFmpeg audio combination with realistic scenarios"""
    
    print("🔧 Testing FFmpeg Audio Combination on Raspberry Pi")
    print("=" * 60)
    
    # Clean up any existing test files
    test_files = ['test_video.mp4', 'test_audio.mp4', 'test_combined.mp4']
    for file in test_files:
        if os.path.exists(file):
            os.remove(file)
    
    try:
        # Step 1: Create a test video (similar to Reddit video format)
        print("📹 Creating test video (silent)...")
        video_cmd = [
            'ffmpeg', '-f', 'lavfi', '-i', 'testsrc=duration=10:size=640x480:rate=30',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23', 
            '-pix_fmt', 'yuv420p', '-y', 'test_video.mp4'
        ]
        
        result = subprocess.run(video_cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"❌ Failed to create test video: {result.stderr}")
            return False
        
        video_size = os.path.getsize('test_video.mp4')
        print(f"✅ Test video created: {video_size} bytes")
        
        # Step 2: Create test audio (similar to Reddit audio format)
        print("🎵 Creating test audio...")
        audio_cmd = [
            'ffmpeg', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=10',
            '-c:a', 'aac', '-b:a', '128k', '-y', 'test_audio.mp4'
        ]
        
        result = subprocess.run(audio_cmd, capture_output=True, text=True, timeout=20)
        if result.returncode != 0:
            print(f"❌ Failed to create test audio: {result.stderr}")
            return False
        
        audio_size = os.path.getsize('test_audio.mp4')
        print(f"✅ Test audio created: {audio_size} bytes")
        
        # Step 3: Test audio+video combination (copy mode)
        print("🎬 Testing audio+video combination (copy mode)...")
        copy_cmd = [
            'ffmpeg', '-i', 'test_video.mp4', '-i', 'test_audio.mp4',
            '-c:v', 'copy', '-c:a', 'copy', '-shortest',
            '-threads', '2', '-y', 'test_combined.mp4'
        ]
        
        print(f"Command: {' '.join(copy_cmd)}")
        result = subprocess.run(copy_cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0 and os.path.exists('test_combined.mp4'):
            combined_size = os.path.getsize('test_combined.mp4')
            print(f"✅ Copy mode successful: {combined_size} bytes")
            
            # Verify the file is valid
            verify_cmd = ['ffprobe', '-v', 'quiet', '-show_format', 'test_combined.mp4']
            verify_result = subprocess.run(verify_cmd, capture_output=True)
            if verify_result.returncode == 0:
                print("✅ Combined file is valid")
            else:
                print("⚠️  Combined file may be corrupted")
            
        else:
            print(f"❌ Copy mode failed: {result.stderr}")
            
            # Step 4: Try re-encoding mode
            print("🔄 Trying re-encoding mode...")
            os.remove('test_combined.mp4') if os.path.exists('test_combined.mp4') else None
            
            encode_cmd = [
                'ffmpeg', '-i', 'test_video.mp4', '-i', 'test_audio.mp4',
                '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k', '-shortest',
                '-threads', '2', '-preset', 'ultrafast', '-y', 'test_combined.mp4'
            ]
            
            print(f"Command: {' '.join(encode_cmd)}")
            result = subprocess.run(encode_cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode == 0 and os.path.exists('test_combined.mp4'):
                combined_size = os.path.getsize('test_combined.mp4')
                print(f"✅ Re-encoding mode successful: {combined_size} bytes")
            else:
                print(f"❌ Re-encoding mode failed: {result.stderr}")
                return False
        
        # Step 5: Performance test
        print("⏱️  Testing performance...")
        import time
        start_time = time.time()
        
        perf_cmd = [
            'ffmpeg', '-i', 'test_video.mp4', '-i', 'test_audio.mp4',
            '-c:v', 'copy', '-c:a', 'aac', '-b:a', '96k', '-shortest',
            '-threads', '2', '-preset', 'ultrafast', '-y', 'perf_test.mp4'
        ]
        
        result = subprocess.run(perf_cmd, capture_output=True, text=True, timeout=120)
        elapsed = time.time() - start_time
        
        if result.returncode == 0:
            print(f"✅ Performance test completed in {elapsed:.2f} seconds")
        else:
            print(f"❌ Performance test failed after {elapsed:.2f} seconds")
        
        # Clean up performance test file
        if os.path.exists('perf_test.mp4'):
            os.remove('perf_test.mp4')
        
        return True
        
    except subprocess.TimeoutExpired:
        print("❌ Test timed out - this indicates performance issues on Raspberry Pi")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    
    finally:
        # Clean up test files
        for file in test_files:
            if os.path.exists(file):
                os.remove(file)

def check_system_resources():
    """Check system resources that affect video processing"""
    print("\n💻 System Resource Check")
    print("=" * 30)
    
    # Check memory
    try:
        with open('/proc/meminfo', 'r') as f:
            meminfo = f.read()
            for line in meminfo.split('\n'):
                if any(keyword in line for keyword in ['MemTotal', 'MemAvailable', 'MemFree', 'SwapTotal', 'SwapFree']):
                    print(f"  {line}")
    except:
        print("  Could not read memory info")
    
    # Check CPU
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
            cpu_count = cpuinfo.count('processor')
            print(f"  CPU cores: {cpu_count}")
            
            # Get CPU model
            for line in cpuinfo.split('\n'):
                if 'model name' in line:
                    print(f"  {line}")
                    break
    except:
        print("  Could not read CPU info")
    
    # Check disk space
    try:
        result = subprocess.run(['df', '-h', '.'], capture_output=True, text=True)
        print("\n  Disk space:")
        for line in result.stdout.split('\n')[1:]:  # Skip header
            if line.strip():
                print(f"    {line}")
    except:
        print("  Could not check disk space")

def test_actual_reddit_scenario():
    """Test with parameters similar to actual Reddit video processing"""
    print("\n🎯 Reddit-like Scenario Test")
    print("=" * 40)
    
    try:
        # Create video similar to Reddit DASH format
        print("Creating Reddit-like video stream...")
        reddit_video_cmd = [
            'ffmpeg', '-f', 'lavfi', '-i', 'testsrc=duration=15:size=720x480:rate=30',
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
            '-movflags', '+faststart', '-y', 'reddit_video.mp4'
        ]
        
        result = subprocess.run(reddit_video_cmd, capture_output=True, text=True, timeout=45)
        if result.returncode != 0:
            print(f"❌ Failed to create Reddit-like video: {result.stderr}")
            return False
        
        # Create audio similar to Reddit DASH audio
        print("Creating Reddit-like audio stream...")
        reddit_audio_cmd = [
            'ffmpeg', '-f', 'lavfi', '-i', 'sine=frequency=880:duration=15',
            '-c:a', 'aac', '-b:a', '128k', '-y', 'reddit_audio.mp4'
        ]
        
        result = subprocess.run(reddit_audio_cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"❌ Failed to create Reddit-like audio: {result.stderr}")
            return False
        
        # Combine using bot's method
        print("Combining using bot's approach...")
        bot_combine_cmd = [
            'ffmpeg', '-i', 'reddit_video.mp4', '-i', 'reddit_audio.mp4',
            '-c:v', 'copy', '-c:a', 'copy', '-map_metadata', '0',
            '-movflags', 'faststart', '-threads', '2', '-y', 'reddit_combined.mp4'
        ]
        
        import time
        start_time = time.time()
        result = subprocess.run(bot_combine_cmd, capture_output=True, text=True, timeout=120)
        elapsed = time.time() - start_time
        
        if result.returncode == 0:
            combined_size = os.path.getsize('reddit_combined.mp4')
            print(f"✅ Reddit scenario successful: {combined_size} bytes in {elapsed:.2f}s")
        else:
            print(f"❌ Reddit scenario failed: {result.stderr}")
            print(f"   Elapsed time: {elapsed:.2f}s")
            return False
        
        return True
        
    except subprocess.TimeoutExpired:
        print("❌ Reddit scenario timed out")
        return False
    except Exception as e:
        print(f"❌ Reddit scenario error: {e}")
        return False
    
    finally:
        # Cleanup
        for file in ['reddit_video.mp4', 'reddit_audio.mp4', 'reddit_combined.mp4']:
            if os.path.exists(file):
                os.remove(file)

def main():
    """Run all diagnostic tests"""
    print("🚀 Raspberry Pi Audio Processing Diagnostic")
    print("=" * 50)
    
    check_system_resources()
    
    success1 = test_ffmpeg_audio_combination()
    success2 = test_actual_reddit_scenario()
    
    print("\n" + "=" * 50)
    if success1 and success2:
        print("🎉 All tests passed! Audio combination should work.")
        print("\nIf your bot still fails, check:")
        print("1. Set RASPBERRY_PI_MODE=true in .env")
        print("2. Set LOG_LEVEL=DEBUG in .env")
        print("3. Check bot logs for specific Reddit URLs that fail")
    else:
        print("❌ Some tests failed. Issues identified:")
        if not success1:
            print("- Basic FFmpeg audio combination is not working")
        if not success2:
            print("- Reddit-like scenario is not working")
        print("\nSuggested fixes:")
        print("1. Increase swap space: sudo dphys-swapfile swapoff && sudo nano /etc/dphys-swapfile")
        print("2. Reduce MAX_POSTS_PER_CHECK=1 in .env")
        print("3. Consider using video-only mode for now")

if __name__ == "__main__":
    main()
