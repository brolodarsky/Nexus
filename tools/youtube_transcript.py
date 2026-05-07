import sys
import os
import datetime
import re
import requests
from youtube_transcript_api import YouTubeTranscriptApi

def get_transcript(video_id):
    try:
        # The API in this version requires an instance and uses fetch()
        return YouTubeTranscriptApi().fetch(video_id)
    except Exception as e:
        print(f"Error fetching transcript: {e}")
        return None

def extract_video_id(url):
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    return url

def get_video_title(video_id):
    try:
        response = requests.get(f"https://www.youtube.com/watch?v={video_id}")
        match = re.search(r"<title>(.*?)</title>", response.text)
        if match:
            title = match.group(1).replace(" - YouTube", "").strip()
            # Clean title for filename
            return re.sub(r'[\\/*?:"<>|]', "", title)
    except Exception as e:
        print(f"Note: Could not fetch video title: {e}")
    return video_id

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python youtube_transcript.py <youtube_url_or_id> [output_file]")
        sys.exit(1)
        
    url_or_id = sys.argv[1]
    video_id = extract_video_id(url_or_id)
    
    print(f"Fetching transcript for video ID: {video_id}...")
    transcript = get_transcript(video_id)

    if transcript:
        title = get_video_title(video_id)
        
        # Define output path
        vault_inbox = os.path.join("Vault", "0. Inbox")
        if not os.path.exists(vault_inbox):
            os.makedirs(vault_inbox)
            
        if len(sys.argv) > 2:
            output_path = sys.argv[2]
        else:
            filename = f"YouTube - {title}.md"
            output_path = os.path.join(vault_inbox, filename)
            
        with open(output_path, 'w', encoding='utf-8') as f:
            # YAML Frontmatter
            f.write("---\n")
            f.write(f"aliases: [\"{title}\"]\n")
            f.write(f"tags: [youtube, transcript, inbox]\n")
            f.write(f"type: capture\n")
            f.write(f"video_id: {video_id}\n")
            f.write(f"url: https://www.youtube.com/watch?v={video_id}\n")
            f.write(f"captured_at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("---\n\n")
            
            f.write(f"# {title}\n\n")
            f.write(f"**Source:** [YouTube](https://www.youtube.com/watch?v={video_id})\n\n")
            f.write("## Transcript\n\n")
            
            for snippet in transcript:
                # Use snippet.text as the elements are objects
                f.write(f"{snippet.text}\n")
                
        print(f"Transcript successfully saved to: {output_path}")
    else:
        print("Failed to retrieve transcript. Check the video ID or ensure subtitles are available.")
