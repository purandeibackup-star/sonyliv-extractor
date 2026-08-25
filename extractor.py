import os
import re
import yt_dlp

# Add the SonyLIV URLs you want in your playlist here
URLS = [
    "https://www.sonyliv.com/shows/indian-game-show-1790007836/celebrities-battle-it-out-1090540334?watch=true"
]

# Pulls the proxy from GitHub Secrets securely
PROXY = os.getenv("PROXY_URL")

def extract_stream_data(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'best'
    }
    
    if PROXY:
        ydl_opts['proxy'] = PROXY
        
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        title = info.get('title', 'Unknown Title')
        
        stream_url = info.get('url') 
        if not stream_url and 'formats' in info:
            stream_url = info['formats'][-1].get('url')
            
        return title, stream_url

def generate_m3u(urls, output_file="playlist.m3u"):
    playlist = ["#EXTM3U\n"]
    
    for url in urls:
        try:
            print(f"Extracting: {url}")
            title, stream_url = extract_stream_data(url)
            
            if not stream_url:
                print(f"Failed to find stream URL for {url}")
                continue
                
            # Regex to find 'id=xxxxxxxxxxxx' inside the hdnea token
            match = re.search(r'id=([0-9]+)', stream_url)
            
            if match:
                playback_id = match.group(1)
                final_url = f"{stream_url}|x-playback-session-id={playback_id}"
            else:
                final_url = stream_url 
                
            playlist.append(f"#EXTINF:-1,{title}\n{final_url}\n")
            print(f"Success: Added {title}")
            
        except Exception as e:
            print(f"Error processing {url}: {e}")
            
    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(playlist)
        print(f"\nSaved to {output_file}")

if __name__ == "__main__":
    generate_m3u(URLS)
