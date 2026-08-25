import os
import re
import sys
import time
import yt_dlp

# Pulls your original SOCKS5 proxy straight from GitHub Secrets
PROXY = os.getenv("PROXY_URL")
SHOWS_FILE = "shows.txt"
PLAYLIST_FILE = "playlist.m3u"

def check_if_update_needed():
    if not os.path.exists(PLAYLIST_FILE):
        print("No existing playlist found. Update required.")
        return True
        
    with open(PLAYLIST_FILE, "r", encoding="utf-8") as f:
        content = f.read()
        
    exp_times = re.findall(r'exp=(\d+)', content)
    
    if not exp_times:
        print("No expiration tokens found in playlist. Update required.")
        return True
        
    current_time = time.time()
    
    for exp in exp_times:
        time_left = int(exp) - current_time
        if time_left < 2100: # 35 minutes
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

def extract_stream_data(url):
    # The exact same options that worked in the beginning!
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'all/best',
        'ignoreerrors': True,
        'extract_flat': False
    }
    
    if PROXY:
        # Pass the SOCKS5 proxy natively without messing with HTTP conversion
        ydl_opts['proxy'] = PROXY 

    # We still keep a small 3-try loop just in case the proxy blinks
    for attempt in range(1, 4):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if info:
                    title = info.get('title', 'Unknown Title')
                    stream_url = info.get('url') 
                    
                    if not stream_url and 'formats' in info:
                        for f in reversed(info['formats']):
                            if f.get('url'):
                                stream_url = f['url']
                                break
                                
                    if stream_url:
                        return title, stream_url
                        
        except Exception as e:
            print(f"Attempt {attempt} failed: {e}")
            
        time.sleep(2)
        
    return None, None

def generate_m3u():
    if not check_if_update_needed():
        sys.exit(0)
        
    urls = load_urls()
    playlist = ["#EXTM3U\n"]
    logo = "https://origin-staticv2.sonyliv.com/UI_icons/sonyliv_new_revised_header_logo.png"
    group = "SonyLIV"
    extracted_count = 0
    
    for url in urls:
        print(f"Extracting: {url}")
        title, stream_url = extract_stream_data(url)
        
        if not stream_url:
            print(f"Failed to find stream URL for {url}")
            continue
            
        match = re.search(r'id=([0-9]+)', stream_url)
        if match:
            playback_id = match.group(1)
            final_url = f"{stream_url}|x-playback-session-id={playback_id}"
        else:
            final_url = stream_url 
            
        playlist.append(f'#EXTINF:-1 group-title="{group}" tvg-logo="{logo}",{title}\n{final_url}\n')
        extracted_count += 1
        print(f"Success: Added {title}")
        
    if extracted_count == 0:
        print("FATAL ERROR: No streams were extracted. Failing the workflow.")
        sys.exit(1)
        
    with open(PLAYLIST_FILE, "w", encoding="utf-8") as f:
        f.writelines(playlist)
        
    print(f"\nSaved {extracted_count} items to {PLAYLIST_FILE}")

if __name__ == "__main__":
    generate_m3u()
