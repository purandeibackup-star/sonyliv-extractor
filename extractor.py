import os
import re
import yt_dlp

# You can put season URLs or direct episode URLs here
URLS = [
    "https://www.sonyliv.com/shows/indian-game-show-1790007836/season/2"
]

PROXY = os.getenv("PROXY_URL")

def extract_manifest_url(info):
    """Safely finds the manifest URL (.mpd or .m3u8) across formats."""
    # 1. Direct url field
    if info.get('url'):
        return info['url']
        
    # 2. Search inside formats list
    formats = info.get('formats', [])
    if formats:
        # Prefer manifest formats (mpd/m3u8) or pick the last available
        for f in reversed(formats):
            if f.get('url'):
                return f['url']
                
    return None

def process_video_entry(info):
    title = info.get('title', 'Unknown Title')
    stream_url = extract_manifest_url(info)
    return title, stream_url

def extract_stream_data(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        # Allow any format including raw DASH/HLS manifests
        'format': 'all/best',
        'extract_flat': False,
        'ignoreerrors': True
    }
    
    if PROXY:
        ydl_opts['proxy'] = PROXY
        
    extracted_videos = []
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        
        if not info:
            return extracted_videos
            
        # Check if the URL resolved to a playlist/season
        if 'entries' in info:
            episodes = [e for e in info['entries'] if e]
            print(f"Found {len(episodes)} entries in playlist.")
            for entry in episodes:
                extracted_videos.append(process_video_entry(entry))
        else:
            extracted_videos.append(process_video_entry(info))
            
    return extracted_videos

def generate_m3u(urls, output_file="playlist.m3u"):
    playlist = ["#EXTM3U\n"]
    
    for url in urls:
        try:
            print(f"\nProcessing: {url}")
            videos = extract_stream_data(url)
            
            for title, stream_url in videos:
                if not stream_url:
                    print(f"Skipping (no stream URL found): {title}")
                    continue
                    
                # Extract 'id=' token value for x-playback header
                match = re.search(r'id=([0-9]+)', stream_url)
                
                if match:
                    playback_id = match.group(1)
                    final_url = f"{stream_url}|x-playback-session-id={playback_id}"
                else:
                    final_url = stream_url 
                    
                playlist.append(f"#EXTINF:-1,{title}\n{final_url}\n")
                print(f"Success: {title}")
                
        except Exception as e:
            print(f"Error processing {url}: {e}")
            
    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(playlist)
        
    items_count = len(playlist) - 1
    print(f"\nFinished! Added {items_count} streams to {output_file}")

if __name__ == "__main__":
    generate_m3u(URLS)
