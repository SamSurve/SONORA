import os
import re
from flask import Flask, render_template, request
import yt_dlp

app = Flask(__name__)

DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

def is_valid_link(url):
    youtube_regex = (
        r'(https?://)?(www\.|music\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|playlist\?list=|embed/|v/|.+\?v=|.+\?list=)?([^&=%\?]+)'
    )
    return re.match(youtube_regex, url) is not None

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    url = request.form.get('url')

    if not url or not is_valid_link(url):
        return "<h1>❌ Invalid Link</h1><p>Check if the playlist is Public/Unlisted.</p><a href='/'>Go Back</a>"

    ydl_opts = {
        'format': 'bestaudio/best',
        # Uses 001, 002 numbering for perfect sorting up to 999 songs
        'outtmpl': f'{DOWNLOAD_FOLDER}/%(playlist_index)03d - %(title)s.%(ext)s',
        'noplaylist': False,
        'ignoreerrors': True,
        'ffmpeg_location': './', 
        'writethumbnail': True,
        'postprocessors': [
            {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'},
            {'key': 'EmbedThumbnail'},
            {'key': 'FFmpegMetadata'},
        ],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return "<h1>✅ Auralis Success!</h1><p>New tracks added with 001-999 numbering.</p><a href='/'>More</a>"
    except Exception as e:
        return f"<h1>Error</h1><p>{str(e)}</p><a href='/'>Try again</a>"

if __name__ == '__main__':
    app.run(debug=True, port=5000, threaded=True)