import os
import re
import requests
import yt_dlp

URLS = [
    "https://www.sonyliv.com/shows/indian-game-show-1790007836/season/2"
]

PROXY = os.getenv("PROXY_URL")

def get_episode_urls_from_season(season_url):
    print(f"Scraping season page for episodes: {season_url}")
    try:
        # Mask the request as a normal browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        # Apply your SOCKS5 proxy to the requests library
        proxies = None
        if PROXY:
            proxies = {
                'http': PROXY,
                'https': PROXY
            }
            
        response = requests.get(season_url, headers=headers, proxies=proxies, timeout=20)
        response.raise_for_status()
        html = response.text
        
        match = re.search(r'/shows/([^/]+-\d+)/', season_url)
        if not match:
            print("Could not parse show ID from season URL.")
            return []
            
        show_path = match.group(1)
        pattern = rf'/shows/{show_path}/[a-zA-Z0-9-]+-\d{{10}}'
        links = re.findall(pattern, html)
        
        episode_urls = []
        seen = set()
        for link in links:
            if link not in seen:
                seen.add(link)
                episode_urls.append(f"https://www.sonyliv.com{link}?watch=true")
                
        print(f"Found {len(episode_urls)} episodes on the season page.")
        return episode_urls
        
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
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'all/best',
        'extract_flat': False,
        'ignoreerrors': True
    }
    
    if PROXY:
        ydl_opts['proxy'] = PROXY
        
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            return None, None
            
        return process_video_entry(info)

def generate_m3u(urls, output_file="playlist.m3u"):
    playlist = ["#EXTM3U\n"]
    
    final_urls = []
    for url in urls:
        if "/season/" in url:
            final_urls.extend(get_episode_urls_from_season(url))
        else:
            final_urls.append(url)
            
    for url in final_urls:
        try:
            print(f"\nProcessing: {url}")
            title, stream_url = extract_stream_data(url)
            
            if not stream_url:
                print(f"Skipping (no stream URL found): {url}")
                continue
                
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
