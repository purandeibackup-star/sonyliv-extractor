import os
import re
import sys
import time
import yt_dlp

PROXY = os.getenv("PROXY_URL")
SHOWS_FILE = "shows.txt"
PLAYLIST_FILE = "playlist.m3u"

def check_if_update_needed():
    # If triggered by a manual push (like editing shows.txt), force an update immediately!
    if os.getenv("GITHUB_EVENT_NAME") == "push":
        print("Detected changes in shows.txt. Forcing immediate update.")
        return True

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
        if time_left < 2100:  # 35 minutes
            print(f"Token expires in {int(time_left/60)} minutes. Update required.")
            return True
            
    print(f"Tokens are still valid. Skipping update.")
    return False

def load_shows():
    if not os.path.exists(SHOWS_FILE):
        with open(SHOWS_FILE, "w") as f:
            f.write("https://www.sonyliv.com/shows/indian-game-show-1790007836/celebrities-battle-it-out-1090540334?watch=true | SonyLIV\n")
    
    shows = []
    with open(SHOWS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            if "|" in line:
                url, group = line.split("|", 1)
                shows.append((url.strip(), group.strip()))
            else:
                shows.append((line, "SonyLIV"))
    return shows

def clean_title(title):
    title = re.sub(r'\s*-\s*SonyLIV$', '', title, flags=re.IGNORECASE)
    return title.strip()

def extract_stream_data(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestvideo+bestaudio/best',
        'extractor_args': {'sonyliv': {'formats': 'dash'}},
        'ignoreerrors': True,
        'extract_flat': False,
        'socket_timeout': 30,
    }
    
    if PROXY:
        ydl_opts['proxy'] = PROXY

    for attempt in range(1, 5):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    title = clean_title(info.get('title', 'Unknown Title'))
                    stream_url = None
                    
                    formats = info.get('formats', [])
                    for f in reversed(formats):
                        f_url = f.get('url', '')
                        if '.mpd' in f_url:
                            stream_url = f_url
                            break
                            
                    if not stream_url:
                        general_url = info.get('url', '')
                        if '.mpd' in general_url:
                            stream_url = general_url
                            
                    if stream_url:
                        return title, stream_url
        except Exception as e:
            print(f"Attempt {attempt} failed due to proxy/network issue: {e}")
            
        print(f"Retrying in 5 seconds...")
        time.sleep(5)
        
    return None, None

def generate_m3u():
    if not check_if_update_needed():
        sys.exit(0)
        
    shows = load_shows()
    playlist = ["#EXTM3U\n"]
    logo = "https://origin-staticv2.sonyliv.com/UI_icons/sonyliv_new_revised_header_logo.png"
    extracted_count = 0
    
    for url, group_name in shows:
        print(f"Extracting: {url} [Group: {group_name}]")
        title, stream_url = extract_stream_data(url)
        
        if not stream_url:
            print(f"Failed to find MPD stream URL for {url}")
            continue
            
        match = re.search(r'id=([0-9]+)', stream_url)
        if match:
            playback_id = match.group(1)
            final_url = f"{stream_url}|x-playback-session-id={playback_id}"
        else:
            path_match = re.search(r'/DASH/([a-fA-F0-9]{32})/', stream_url)
            if path_match:
                playback_id = path_match.group(1)
                final_url = f"{stream_url}|x-playback-session-id={playback_id}"
            else:
                final_url = f"{stream_url}|x-playback-session-id=98404716139163545924947790596008"
            
        playlist.append(f'#EXTINF:-1 group-title="{group_name}" tvg-logo="{logo}",{title}\n{final_url}\n')
        extracted_count += 1
        print(f"Success: Added {title}")
        
    if extracted_count == 0:
        print("FATAL ERROR: No MPD streams were extracted. Failing the workflow.")
        sys.exit(1)
        
    with open(PLAYLIST_FILE, "w", encoding="utf-8") as f:
        f.writelines(playlist)
        
    print(f"\nSaved {extracted_count} items to {PLAYLIST_FILE}")

if __name__ == "__main__":
    generate_m3u()
