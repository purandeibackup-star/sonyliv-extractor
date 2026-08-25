import os
import re
import sys
import time
import yt_dlp
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PROXY = os.getenv("PROXY_URL")
SHOWS_FILE = "shows.txt"
PLAYLIST_FILE = "playlist.m3u"

def check_if_update_needed():
    """Checks the exp= token in the existing playlist to see if it expires soon."""
    if not os.path.exists(PLAYLIST_FILE):
        print("No existing playlist found. Update required.")
        return True
        
    with open(PLAYLIST_FILE, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Find all expiration timestamps in the M3U file
    exp_times = re.findall(r'exp=(\d+)', content)
    
    if not exp_times:
        print("No expiration tokens found in playlist. Update required.")
        return True
        
    current_time = time.time()
    
    for exp in exp_times:
        time_left = int(exp) - current_time
        # If the token expires in less than 35 minutes (2100 seconds), update it!
        if time_left < 2100:
            print(f"Token expires in {int(time_left/60)} minutes. Update required.")
            return True
            
    print(f"Tokens are still valid for another {int((int(exp_times[0]) - current_time)/60)} minutes. Skipping update.")
    return False

def load_urls():
    if not os.path.exists(SHOWS_FILE):
        with open(SHOWS_FILE, "w") as f:
            f.write("https://www.sonyliv.com/shows/indian-game-show-1790007836/celebrities-battle-it-out-1090540334?watch=true\n")
    
    with open(SHOWS_FILE, "r") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

def extract_manifest_url(info):
    if info.get('url'):
        return info['url']
    formats = info.get('formats', [])
    for f in reversed(formats):
        if f.get('url'):
            return f['url']
    return None

def extract_stream_data(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'all/best',
        'ignoreerrors': True,
        'nocheckcertificate': True
    }
    
    if PROXY:
        ydl_opts['proxy'] = PROXY.replace("socks5://", "http://").replace("socks5h://", "http://")
        
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            return None, None
            
        title = info.get('title', 'Unknown Title')
        stream_url = extract_manifest_url(info)
        return title, stream_url

def generate_m3u():
    if not check_if_update_needed():
        sys.exit(0) # Exits cleanly with a Green Tick, doing nothing.
        
    urls = load_urls()
    playlist = ["#EXTM3U\n"]
    logo = "https://origin-staticv2.sonyliv.com/UI_icons/sonyliv_new_revised_header_logo.png"
    group = "SonyLIV"
    
    extracted_count = 0
    
    for url in urls:
        print(f"Extracting: {url}")
        title, stream_url = extract_stream_data(url)
        
        if not stream_url:
            print(f"Failed to extract stream for: {url}")
            continue
            
        match = re.search(r'id=([0-9]+)', stream_url)
        if match:
            playback_id = match.group(1)
            final_url = f"{stream_url}|x-playback-session-id={playback_id}"
        else:
            final_url = stream_url 
            
        playlist.append(f'#EXTINF:-1 group-title="{group}" tvg-logo="{logo}",{title}\n{final_url}\n')
        extracted_count += 1
        
    if extracted_count == 0:
        print("FATAL ERROR: Failed to extract any streams. Failing the workflow.")
        sys.exit(1)
        
    with open(PLAYLIST_FILE, "w", encoding="utf-8") as f:
        f.writelines(playlist)
        
    print(f"Successfully generated playlist with {extracted_count} streams.")

if __name__ == "__main__":
    generate_m3u()
