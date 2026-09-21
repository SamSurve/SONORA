import yt_dlp
import os

def download_and_arrange(url):
    # Ensures Python knows exactly where your ffmpeg.exe is located
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'ffmpeg_location': base_dir,
        # Organizes by uploader and album automatically
        'outtmpl': 'MyMusic/%(uploader)s/%(album)s/%(playlist_index)02d - %(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320', # Forces highest quality 320kbps
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

# PASTE YOUR LINK HERE
my_link = "https://music.youtube.com/playlist?list=PLssTpFClN4KUydeu-LiTup-AHZkNCXKJs&si=ku4F24MqaFXGsbXx"
download_and_arrange(my_link)