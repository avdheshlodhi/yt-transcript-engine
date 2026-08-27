from http.server import BaseHTTPRequestHandler
from youtube_transcript_api import YouTubeTranscriptApi
import urllib.parse
import json
import re

def extract_video_id(url):
    pattern = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url)
    return match.group(1) if match else None

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_path.query)
        video_url = query_params.get('url', [None])[0]

        # CORS Headers (Taaki aapki Hostinger website isse connect ho sake)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'X-Requested-With, Content-Type')
        self.end_headers()

        if not video_url:
            self.wfile.write(json.dumps({'error': 'URL missing!'}).encode())
            return

        video_id = extract_video_id(video_url)
        if not video_id:
            self.wfile.write(json.dumps({'error': 'Invalid YouTube URL!'}).encode())
            return

        try:
            # Python standard scraper engine (Bypass network policy)
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'hi'])
            formatted_transcript = []
            
            for entry in transcript_list:
                start_time = int(entry['start'])
                timestamp = f"{start_time // 60:02d}:{start_time % 60:02d}"
                formatted_transcript.append({'timestamp': timestamp, 'text': entry['text']})
            
            self.wfile.write(json.dumps({'success': True, 'transcript': formatted_transcript}).encode())

        except Exception as e:
            self.wfile.write(json.dumps({'error': 'Captions are unavailable or video is restricted.'}).encode())
