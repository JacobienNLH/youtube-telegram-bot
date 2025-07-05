import logging
import os
import tempfile
import re
from typing import Optional, Dict, Any

import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters
)

from config import BOT_TOKEN, LIKES_THRESHOLD

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class YouTubeBot:
    def __init__(self, token: str, likes_threshold: int = 10):
        self.token = token
        self.likes_threshold = likes_threshold
        self.app = Application.builder().token(token).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Set up all bot handlers"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome_message = (
            "🎥 Welcome to YouTube Downloader Bot!\n\n"
            "Send me a YouTube URL and I'll help you download it if it has enough likes.\n\n"
            f"📊 Minimum likes required: {self.likes_threshold}\n\n"
            "Use /help for more information."
        )
        await update.message.reply_text(welcome_message)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_message = (
            "📋 How to use this bot:\n\n"
            "1. Send me a YouTube URL\n"
            "2. I'll check if the video has enough likes\n"
            f"3. If it has more than {self.likes_threshold} likes, you can download it\n"
            "4. Choose between MP4 (video) or MP3 (audio) format\n"
            "5. I'll send you the file directly\n\n"
            "🔗 Supported formats:\n"
            "• https://www.youtube.com/watch?v=VIDEO_ID\n"
            "• https://youtu.be/VIDEO_ID\n"
            "• https://www.youtube.com/shorts/VIDEO_ID\n"
            "• https://m.youtube.com/watch?v=VIDEO_ID\n\n"
            "⚠️ Note: Only videos with sufficient likes can be downloaded."
        )
        await update.message.reply_text(help_message)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages"""
        message_text = update.message.text
        
        if self.is_youtube_url(message_text):
            await self.process_youtube_url(update, context, message_text)
        else:
            await update.message.reply_text(
                "Please send me a valid YouTube URL.\n\n"
                "Supported formats:\n"
                "• https://www.youtube.com/watch?v=VIDEO_ID\n"
                "• https://youtu.be/VIDEO_ID\n"
                "• https://www.youtube.com/shorts/VIDEO_ID\n"
                "• https://m.youtube.com/watch?v=VIDEO_ID"
            )
    
    def is_youtube_url(self, url: str) -> bool:
        """Check if the URL is a valid YouTube URL"""
        youtube_patterns = [
            # Regular YouTube URLs
            r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+',
            r'(?:https?://)?(?:www\.)?youtu\.be/[\w-]+',
            r'(?:https?://)?(?:m\.)?youtube\.com/watch\?v=[\w-]+',
            # YouTube Shorts URLs
            r'(?:https?://)?(?:www\.)?youtube\.com/shorts/[\w-]+',
            r'(?:https?://)?(?:m\.)?youtube\.com/shorts/[\w-]+',
            # YouTube URLs with additional parameters
            r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+(&.*)?',
            r'(?:https?://)?(?:www\.)?youtube\.com/shorts/[\w-]+(\?.*)?',
        ]
        return any(re.match(pattern, url) for pattern in youtube_patterns)
    
    async def get_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Get video information using yt-dlp"""
        try:
            # Multiple extraction strategies with SSL fixes
            ydl_opts_list = [
                # Strategy 1: Default options
                {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': False,
                },
                # Strategy 2: Disable SSL verification (for corporate networks)
                {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': False,
                    'nocheckcertificate': True,
                },
                # Strategy 3: With custom headers and no SSL check
                {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': False,
                    'nocheckcertificate': True,
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    }
                },
                # Strategy 4: Alternative extractor settings
                {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': False,
                    'nocheckcertificate': True,
                    'prefer_insecure': True,
                }
            ]
            
            # Try each strategy
            for i, ydl_opts in enumerate(ydl_opts_list):
                try:
                    logger.info(f"Trying extraction strategy {i+1}")
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        logger.info(f"Successfully extracted with strategy {i+1}")
                        return {
                            'title': info.get('title', 'Unknown'),
                            'uploader': info.get('uploader', 'Unknown'),
                            'duration': info.get('duration', 0),
                            'like_count': info.get('like_count', 0),
                            'view_count': info.get('view_count', 0),
                            'url': url,
                            'id': info.get('id', ''),
                            'thumbnail': info.get('thumbnail', '')
                        }
                except Exception as strategy_error:
                    logger.warning(f"Strategy {i+1} failed: {strategy_error}")
                    continue
            
            # If all strategies fail
            logger.error("All extraction strategies failed")
            return None
            
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return None
    
    async def process_youtube_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
        """Process YouTube URL and check likes"""
        # Send processing message
        processing_msg = await update.message.reply_text("🔍 Checking video information...")
        
        # Get video info
        video_info = await self.get_video_info(url)
        
        if not video_info:
            await processing_msg.edit_text(
                "❌ Error: Could not retrieve video information.\n\n"
                "This could be due to:\n"
                "• Video is private or restricted\n"
                "• Invalid YouTube URL\n"
                "• yt-dlp needs updating\n\n"
                "Please try:\n"
                "1. A different video\n"
                "2. Updating the bot (if you're the admin)\n"
                "3. Checking if the video is publicly accessible"
            )
            return
        
        # Check likes threshold
        likes = video_info.get('like_count', 0)
        title = video_info.get('title', 'Unknown')
        uploader = video_info.get('uploader', 'Unknown')
        duration = self.format_duration(video_info.get('duration', 0))
        
        if likes < self.likes_threshold:
            await processing_msg.edit_text(
                f"❌ Sorry, this video doesn't meet the minimum likes requirement.\n\n"
                f"📺 Title: {title}\n"
                f"👤 Uploader: {uploader}\n"
                f"👍 Likes: {likes:,}\n"
                f"📊 Required: {self.likes_threshold:,}\n\n"
                "Please try a video with more likes."
            )
            return
        
        # Video meets requirements, show download options
        context.user_data['video_info'] = video_info
        
        keyboard = [
            [
                InlineKeyboardButton("🎥 Download MP4 (Video)", callback_data="download_mp4"),
                InlineKeyboardButton("🎵 Download MP3 (Audio)", callback_data="download_mp3")
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await processing_msg.edit_text(
            f"✅ Video approved for download!\n\n"
            f"📺 Title: {title}\n"
            f"👤 Uploader: {uploader}\n"
            f"⏱️ Duration: {duration}\n"
            f"👍 Likes: {likes:,}\n\n"
            "Choose your preferred format:",
            reply_markup=reply_markup
        )
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "cancel":
            await query.edit_message_text("❌ Download cancelled.")
            return
        
        video_info = context.user_data.get('video_info')
        if not video_info:
            await query.edit_message_text("❌ Error: Video information not found. Please try again.")
            return
        
        if query.data == "download_mp4":
            await self.download_and_send(query, video_info, "mp4")
        elif query.data == "download_mp3":
            await self.download_and_send(query, video_info, "mp3")
    
    async def download_and_send(self, query, video_info: Dict[str, Any], format_type: str):
        """Download video/audio and send to user"""
        title = video_info.get('title', 'Unknown')
        url = video_info.get('url', '')
        
        # Update message to show download progress
        await query.edit_message_text(
            f"⬇️ Downloading {format_type.upper()}...\n\n"
            f"📺 Title: {title}\n"
            f"Please wait, this may take a few moments."
        )
        
        try:
            # Create temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                if format_type == "mp4":
                    success, file_path = await self.download_video(url, temp_dir, title)
                else:  # mp3
                    success, file_path = await self.download_audio(url, temp_dir, title)
                
                if success and file_path and os.path.exists(file_path):
                    # Send file to user
                    await query.edit_message_text(
                        f"📤 Sending {format_type.upper()} file...\n\n"
                        f"📺 Title: {title}"
                    )
                    
                    with open(file_path, 'rb') as file:
                        if format_type == "mp4":
                            await query.message.reply_video(
                                video=file,
                                caption=f"🎥 {title}",
                                supports_streaming=True
                            )
                        else:  # mp3
                            await query.message.reply_audio(
                                audio=file,
                                caption=f"🎵 {title}"
                            )
                    
                    await query.edit_message_text(
                        f"✅ {format_type.upper()} sent successfully!\n\n"
                        f"📺 Title: {title}"
                    )
                else:
                    await query.edit_message_text(
                        f"❌ Error downloading {format_type.upper()}.\n"
                        "Please try again later."
                    )
        
        except Exception as e:
            logger.error(f"Error in download_and_send: {e}")
            await query.edit_message_text(
                f"❌ Error downloading {format_type.upper()}.\n"
                f"Error: {str(e)}"
            )
    
    async def download_video(self, url: str, output_dir: str, title: str) -> tuple[bool, Optional[str]]:
        """Download video in MP4 format"""
        try:
            safe_title = self.sanitize_filename(title)
            output_path = os.path.join(output_dir, f"{safe_title}.%(ext)s")
            
            ydl_opts = {
                'format': 'best[ext=mp4]/mp4/best',
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,  # Fix SSL issues
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # Find the downloaded file
            for file in os.listdir(output_dir):
                if file.startswith(safe_title):
                    return True, os.path.join(output_dir, file)
            
            return False, None
            
        except Exception as e:
            logger.error(f"Error downloading video: {e}")
            return False, None
    
    async def download_audio(self, url: str, output_dir: str, title: str) -> tuple[bool, Optional[str]]:
        """Download audio in best available format (MP3 if FFmpeg available, otherwise original format)"""
        try:
            safe_title = self.sanitize_filename(title)
            output_path = os.path.join(output_dir, f"{safe_title}.%(ext)s")
            
            # Check if FFmpeg is available
            import shutil
            ffmpeg_path = shutil.which('ffmpeg')
            
            if ffmpeg_path:
                logger.info(f"FFmpeg found at: {ffmpeg_path} - Converting to MP3")
                # FFmpeg available - convert to MP3
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': output_path,
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                    'quiet': False,
                    'nocheckcertificate': True,
                }
                expected_extension = '.mp3'
            else:
                logger.info("FFmpeg not found - Downloading original audio format")
                # No FFmpeg - download best audio format available
                ydl_opts = {
                    'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',
                    'outtmpl': output_path,
                    'quiet': False,
                    'nocheckcertificate': True,
                }
                expected_extension = None  # Will check for any audio format
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # Find the downloaded file
            logger.info(f"Looking for files in: {output_dir}")
            files_found = os.listdir(output_dir)
            logger.info(f"Files found: {files_found}")
            
            # Look for the specific file format first
            if expected_extension:
                for file in files_found:
                    if file.startswith(safe_title) and file.endswith(expected_extension):
                        logger.info(f"Found audio file: {file}")
                        return True, os.path.join(output_dir, file)
            
            # Look for any audio file
            audio_extensions = ['.mp3', '.m4a', '.webm', '.ogg', '.aac', '.opus']
            for file in files_found:
                if file.startswith(safe_title):
                    for ext in audio_extensions:
                        if file.endswith(ext):
                            logger.info(f"Found audio file: {file}")
                            return True, os.path.join(output_dir, file)
            
            # If no match with title, look for any audio file
            for file in files_found:
                for ext in audio_extensions:
                    if file.endswith(ext):
                        logger.info(f"Found audio file (any): {file}")
                        return True, os.path.join(output_dir, file)
            
            logger.error("No audio files found after download")
            return False, None
            
        except Exception as e:
            logger.error(f"Error downloading audio: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return False, None
    
    def sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe file system usage"""
        # Remove or replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Limit length
        if len(filename) > 100:
            filename = filename[:100]
        
        return filename.strip()
    
    def format_duration(self, seconds: int) -> str:
        """Format duration from seconds to readable format"""
        if seconds == 0:
            return "Unknown"
        
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"
    
    def run(self):
        """Start the bot"""
        logger.info("Starting YouTube Downloader Bot...")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)

def main():
    """Main function to run the bot"""
    bot = YouTubeBot(BOT_TOKEN, LIKES_THRESHOLD)
    bot.run()

if __name__ == "__main__":
    main()
