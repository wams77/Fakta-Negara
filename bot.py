import os
import random
import json
import requests
import asyncio
import edge_tts
from groq import Groq
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip
import moviepy.video.fx.all as vfx

# ==========================================
# 1. KONFIGURASI API KEY DARI ENVIRONMENT
# ==========================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
YOUTUBE_TOKEN = os.environ.get("YOUTUBE_TOKEN")

# Daftar negara yang akan dipilih secara acak oleh bot
NEGARA_LIST = [
    "Jepang", "Islandia", "Italia", "Meksiko", "Mesir", 
    "Kanada", "Swiss", "India", "Brasil", "Turki", "Korea Selatan"
]

# ==========================================
# 2. FUNGSI GENERATE NASKAH (GROQ API)
# ==========================================
def get_script_from_groq(negara):
    print(f"[*] Meminta naskah untuk {negara} dari Groq API...")
    client = Groq(api_key=GROQ_API_KEY)
    
    prompt = f"""Kamu adalah pembuat konten YouTube Shorts. Buatkan 3 fakta unik tentang kehidupan, tradisi, atau budaya di negara {negara}. 
    Naskah harus berbahasa Indonesia, santai, dan durasi jika dibaca maksimal 45 detik.
    Berikan juga 1 kata kunci bahasa Inggris (maksimal 3 kata) yang spesifik dan visual untuk mencari video latar di Pexels (contoh: "Tokyo neon night", "Iceland snow", "Rome street").
    Wajib balas HANYA dengan format JSON seperti ini:
    {{
        "judul": "Judul Shorts yang menarik",
        "deskripsi": "Deskripsi singkat video dan 3 hashtag",
        "naskah": "Teks naskah lengkap",
        "query_pexels": "kata kunci"
    }}"""

    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="mixtral-8x7b-32768",
        response_format={"type": "json_object"}
    )
    
    return json.loads(response.choices[0].message.content)

# ==========================================
# 3. FUNGSI TEXT-TO-SPEECH (EDGE TTS)
# ==========================================
async def create_voiceover(text, output_filename="audio.mp3"):
    print("[*] Membuat Voiceover (Text-to-Speech)...")
    # Menggunakan suara wanita Indonesia (GadisNeural)
    communicate = edge_tts.Communicate(text, "id-ID-GadisNeural")
    await communicate.save(output_filename)

# ==========================================
# 4. FUNGSI UNDUH VIDEO Latar (PEXELS API)
# ==========================================
def download_pexels_video(query, output_filename="background.mp4"):
    print(f"[*] Mencari video di Pexels untuk kata kunci: '{query}'...")
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={query}&orientation=portrait&per_page=1"
    
    response = requests.get(url, headers=headers).json()
    if not response.get("videos"):
        raise Exception(f"Video tidak ditemukan di Pexels untuk query: {query}")
    
    # Ambil link video dengan kualitas HD (tinggi >= 1080)
    video_files = response["videos"][0]["video_files"]
    hd_file = next((file for file in video_files if file["height"] >= 1080), video_files[0])
    video_url = hd_file["link"]
    
    print("[*] Mengunduh video...")
    with requests.get(video_url, stream=True) as r:
        r.raise_for_status()
        with open(output_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

# ==========================================
# 5. FUNGSI RENDER VIDEO (MOVIEPY)
# ==========================================
def render_video(json_data):
    print("[*] Memulai proses render video...")
    
    audio = AudioFileClip("audio.mp3")
    video = VideoFileClip("background.mp4")
    
    # Logika Durasi: Jika video lebih pendek dari audio, ulang (loop) videonya
    if video.duration < audio.duration:
        print("[!] Video lebih pendek dari audio. Melakukan looping video...")
        video = video.fx(vfx.loop, duration=audio.duration)
    else:
        video = video.subclip(0, audio.duration)
        
    video = video.set_audio(audio)
    
    # Tambahkan Teks Judul di tengah atas video
    try:
        txt_clip = TextClip(
            json_data["judul"], 
            fontsize=40, 
            color='white', 
            bg_color='rgba(0,0,0,0.5)', 
            method='caption', 
            size=(video.w - 100, None)
        )
        txt_clip = txt_clip.set_pos(('center', 'center')).set_duration(video.duration)
        final_video = CompositeVideoClip([video, txt_clip])
    except Exception as e:
        print(f"[!] Gagal membuat teks (ImageMagick error), merender tanpa teks. Error: {e}")
        final_video = video
    
    print("[*] Mengekspor hasil akhir (Ini akan memakan waktu)...")
    # Setting CPU threads agar tidak crash di GitHub Actions
    final_video.write_videofile(
        "hasil_shorts.mp4", 
        fps=24, 
        codec="libx264", 
        audio_codec="aac", 
        threads=2, 
        preset="ultrafast"
    )
    print("[+] Video berhasil dibuat: hasil_shorts.mp4")

# ==========================================
# 6. FUNGSI UPLOAD YOUTUBE API
# ==========================================
def upload_to_youtube(video_file, judul, deskripsi):
    print("[*] Memulai proses upload ke YouTube...")
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials

    if not YOUTUBE_TOKEN:
        raise Exception("YOUTUBE_TOKEN tidak ditemukan di environment variables.")
        
    # Buat file token.json sementara dari text rahasia GitHub
    with open("token.json", "w") as f:
        f.write(YOUTUBE_TOKEN)
        
    try:
        creds = Credentials.from_authorized_user_file('token.json', ['https://www.googleapis.com/auth/youtube.upload'])
        youtube = build('youtube', 'v3', credentials=creds)
        
        body = {
            'snippet': {
                'title': judul[:100], # YouTube membatasi judul max 100 karakter
                'description': deskripsi,
                'tags': ['shorts', 'faktaunik', 'negaradunia', 'faktamenarik'],
                'categoryId': '22' # People & Blogs
            },
            'status': {
                'privacyStatus': 'private', # Default 'private' untuk uji coba. Ubah ke 'public' jika sudah siap.
                'selfDeclaredMadeForKids': False
            }
        }
        
        media = MediaFileUpload(video_file, chunksize=-1, resumable=True, mimetype='video/mp4')
        request = youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )
        
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"[*] Uploading... {int(status.progress() * 100)}%")
                
        print(f"[+] Upload Selesai! ID Video: {response['id']}")
    finally:
        # Hapus token dari server setelah selesai untuk keamanan
        if os.path.exists("token.json"):
            os.remove("token.json")

# ==========================================
# 7. MAIN FUNCTION (EKSEKUSI UTAMA)
# ==========================================
async def main():
    negara = random.choice(NEGARA_LIST)
    print(f"=== MEMULAI BOT UNTUK NEGARA: {negara.upper()} ===")
    
    try:
        # Tahap 1: Generate Konten
        konten = get_script_from_groq(negara)
        print("Data JSON dari Groq:", json.dumps(konten, indent=2))
        
        # Tahap 2: Text-to-Speech
        await create_voiceover(konten["naskah"])
        
        # Tahap 3: Download Video
        download_pexels_video(konten["query_pexels"])
        
        # Tahap 4: Render Video Final
        render_video(konten)
        
        # Tahap 5: Upload ke YouTube
        deskripsi_lengkap = f"{konten['deskripsi']}\n\nVideo Footage by Pexels\nScript by Groq AI\nVoice by Edge-TTS"
        upload_to_youtube("hasil_shorts.mp4", konten["judul"], deskripsi_lengkap)
        
        print("=== SEMUA PROSES BERHASIL SELESAI ===")
        
    except Exception as e:
        print(f"[-] Terjadi kesalahan fatal: {e}")

if __name__ == "__main__":
    asyncio.run(main())
