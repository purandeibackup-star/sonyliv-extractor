import os
import re
import sys
import requests
import yt_dlp
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed

# Suppress the SSL proxy warnings in the GitHub console
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PROXY = os.getenv("PROXY_URL")
SHOWS_FILE = "shows.txt"

def load_urls():
    if not os.path.exists(SHOWS_FILE):
        print(f"{SHOWS_FILE} not found. Creating a default one.")
        with open(SHOWS_FILE, "w") as f:
            f.write("https://www.sonyliv.com/shows/indian-game-show-1790007836/season/2\n")
    
    with open(SHOWS_FILE, "r") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

def get_episode_urls_from_season(season_url):
    print(f"Scraping season page for episodes: {season_url}")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        proxies = None
        if PROXY:
            req_proxy = PROXY.replace("socks5://", "http://").replace("socks5h://", "http://")
            proxies = {'http': req_proxy, 'https': req_proxy}
            
        response = requests.get(season_url, headers=headers, proxies=proxies, timeout=20, verify=False)
        response.raise_for_status()
        html = response.text
        
        match = re.search(r'/shows/([^/]+-\d{10})', season_url)
        if not match:
            print("Could not parse show ID from season URL.")
            return []
            
        show_path = match.group(1)
        
        # FIX: Target the exact JSON key to avoid garbage unicode and ad recommendations
        slugs = re.findall(r'"seoUrl":"([^"]+-\d{10})"', html)
        
        # Fallback just in case seoUrl isn't used
        if not slugs:
            raw_slugs = re.findall(r'([a-zA-Z0-9-]+-\d{10})', html)
            slugs = [s for s in raw_slugs if 'u002F' not in s]
        
        episode_urls = []
        seen = set()
        for slug in slugs:
            # Clean up and ensure we aren't pulling in other shows like 'the-legend-of-karna'
            slug = slug.replace('\\u002F', '').replace('u002F', '')
            if slug != show_path and show_path.split('-')[0] not in slug:
                full_link = f"https://www.sonyliv.com/shows/{show_path}/{slug}?watch=true"
                if full_link not in seen:
                    seen.add(full_link)
                    episode_urls.append(full_link)
                    
        print(f"Found {len(episode_urls)} valid episodes.")
        
        recent_episodes = episode_urls[-5:]
        print(f"Limiting to the {len(recent_episodes)} most recent episodes.")
        return recent_episodes
        
    except Exception as e:
        print(f"Error scraping season page: {e}")
        return []

def extract_manifest_url(info):
    if info.get('url'):
        return info['url']
    formats = info.get('formats', [])
    if formats:
        for f in reversed(formats):
            if f.get('url'):
                return f['url']
    return None

def process_video_entry(info):
    title = info.get('title', 'Unknown Title')
    stream_url = extract_manifest_url(info)
    return title, stream_url

def extract_stream_data(url):
    print(f"Thread started: {url}")
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'all/best',
        'extract_flat': False,
        'ignoreerrors': True,
        'nocheckcertificate': True # FIX: Stops the proxy from breaking yt-dlp's SSL handshake
    }
    
    if PROXY:
        ydl_opts['proxy'] = PROXY.replace("socks5://", "http://").replace("socks5h://", "http://")
        
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            return url, None, None
        title, stream_url = process_video_entry(info)
        return url, title, stream_url

def generate_m3u(urls, output_file="playlist.m3u"):
    playlist = ["#EXTM3U\n"]
    
    final_urls = []
    for url in urls:
        if "/season/" in url:
            final_urls.extend(get_episode_urls_from_season(url))
        else:
            final_urls.append(url)
            
    logo = "https://origin-staticv2.sonyliv.com/UI_icons/sonyliv_new_revised_header_logo.png"
    group = "SonyLIV"
    
    extracted_data = []
    
    print(f"\nStarting parallel extraction for {len(final_urls)} streams...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(extract_stream_data, url): url for url in final_urls}
        
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                original_url, title, stream_url = future.result()
                if stream_url:
                    extracted_data.append((title, stream_url))
                else:
                    print(f"Skipping (no stream URL found): {url}")
            except Exception as e:
                print(f"Error processing {url}: {e}")
                
    extracted_data.sort(key=lambda x: x[0]) 

    for title, stream_url in extracted_data:
        match = re.search(r'id=([0-9]+)', stream_url)
        if match:
            playback_id = match.group(1)
            final_url = f"{stream_url}|x-playback-session-id={playback_id}"
        else:
            final_url = stream_url 
            
        playlist.append(f'#EXTINF:-1 group-title="{group}" tvg-logo="{logo}",{title}\n{final_url}\n')
        
    items_count = len(playlist) - 1
    
    if items_count == 0:
        print("\nFATAL ERROR: No streams were extracted. Failing the workflow.")
        sys.exit(1)
        
    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(playlist)
        
    print(f"\nFinished! Added {items_count} streams to {output_file}")

if __name__ == "__main__":
    urls_to_process = load_urls()
    generate_m3u(urls_to_process)
