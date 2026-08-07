import os
import random
import json
import requests
import asyncio
import edge_tts
from groq import Groq
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
import moviepy.video.fx.all as vfx

# ==========================================
# 1. KONFIGURASI API KEY DARI ENVIRONMENT
# ==========================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
YOUTUBE_TOKEN = os.environ.get("YOUTUBE_TOKEN")

# Daftar negara
NEGARA_LIST = [
    "Jepang", "Islandia", "Italia", "Meksiko", "Mesir", 
    "Kanada", "Swiss", "India", "Brasil", "Turki", "Korea Selatan",
    "Belanda", "Norwegia", "Selandia Baru", "Maroko", "Argentina"
]

# ==========================================
# 2. FUNGSI GENERATE NASKAH (DIUPDATE UNTUK B-ROLL CEWEK CANTIK)
# ==========================================
def get_script_from_groq(negara):
    print(f"[*] Meminta naskah untuk {negara} dari Groq API (Llama 3.3 70B)...")
    client = Groq(api_key=GROQ_API_KEY)
    
    prompt = f"""Kamu adalah pembuat konten YouTube Shorts dengan gaya bercerita yang super santai dan ekspresif. 
    Tugasmu membuat naskah video maksimal 45 detik (sekitar 70 kata) tentang 3 KEBIASAAN UNIK, ANEH, atau MENCENGANGKAN dari para CEWEK atau GADIS di negara {negara}.

    ATURAN SANGAT KETAT AGAR SUARA ROBOT TERDENGAR SEPERTI MANUSIA:
    1. WAJIB gunakan bahasa Indonesia tutur/gaul (contoh: "Tahu nggak sih...", "cewek-cewek di sana tuh...", "banget", "bikin geleng kepala", "nah"). Jangan gunakan bahasa kaku!
    2. Perbanyak tanda baca elipsis (...) untuk memaksa jeda napas. Gunakan tanda seru (!) untuk penekanan emosi.
    3. Kalimat pertama WAJIB berupa HOOK yang nyeleneh (Contoh: "Pernah bayangin nggak, cewek di {negara} tuh ternyata kebiasaannya...").
    4. Hindari sapaan basi seperti "Halo teman-teman". Langsung ke inti cerita.
    
    ATURAN UNTUK PEXELS (SANGAT PENTING):
    Berikan 3 kata kunci bahasa Inggris (maks. 3 kata per keyword) untuk mencari 3 video latar di Pexels. 
    - Prioritas UTAMA adalah mencari visual wanita cantik dari negara tersebut (contoh: "beautiful {negara} woman", "pretty {negara} girl", "asian beauty").
    - Jika faktanya terlalu spesifik, padukan visual wanita dengan aktivitasnya (contoh: "woman eating noodle", "girl walking night").

    Wajib balas HANYA dengan format JSON seperti ini tanpa teks pengantar apa pun:
    {{
        "judul": "Judul clickbait dan bikin penasaran tentang cewek",
        "deskripsi": "Deskripsi singkat dan 3 hashtag",
        "naskah": "Teks naskah lengkap dengan gaya bahasa gaul dan tanda baca jeda",
        "query_pexels": ["keyword 1", "keyword 2", "keyword 3"]
    }}"""

    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile", 
        response_format={"type": "json_object"}
    )
    
    return json.loads(response.choices[0].message.content)

# ==========================================
# 3. FUNGSI TEXT-TO-SPEECH (DIUPDATE MENGGUNAKAN SUARA PRIA NATURAL)
# ==========================================
async def create_voiceover(text, output_filename="audio.mp3"):
    print("[*] Membuat Voiceover (Text-to-Speech) dengan suara pria...")
    
    # id-ID-ArdiNeural adalah suara pria. 
    # rate="+5%" ditambahkan opsional jika Anda ingin bicaranya sedikit lebih cepat dan energik.
    communicate = edge_tts.Communicate(text, "id-ID-ArdiNeural", rate="+5%")
    await communicate.save(output_filename)
# ==========================================
# 4. FUNGSI UNDUH MULTIPLE VIDEO (PEXELS API)
# ==========================================
def download_multiple_pexels_videos(queries):
    print(f"[*] Mencari video di Pexels untuk kata kunci: {queries}")
    headers = {"Authorization": PEXELS_API_KEY}
    downloaded_files = []
    
    for idx, query in enumerate(queries):
        url = f"https://api.pexels.com/videos/search?query={query}&orientation=portrait&per_page=1"
        response = requests.get(url, headers=headers).json()
        
        if not response.get("videos"):
            print(f"[!] Video tidak ditemukan untuk query: '{query}'. Melewati...")
            continue
            
        video_files = response["videos"][0]["video_files"]
        hd_file = next((file for file in video_files if file["height"] >= 1080), video_files[0])
        video_url = hd_file["link"]
        
        output_filename = f"bg_{idx}.mp4"
        print(f"[*] Mengunduh video {idx+1}... ({query})")
        
        with requests.get(video_url, stream=True) as r:
            r.raise_for_status()
            with open(output_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
        downloaded_files.append(output_filename)
        
    if not downloaded_files:
        raise Exception("Gagal mengunduh semua video Pexels.")
        
    return downloaded_files

# ==========================================
# 5. FUNGSI RENDER VIDEO GABUNGAN (MOVIEPY)
# ==========================================
def render_video(json_data, video_files):
    print("[*] Memulai proses render penggabungan video...")
    
    audio = AudioFileClip("audio.mp3")
    
    clips = []
    for file in video_files:
        print(f"[*] Memproses klip: {file}")
        clip = VideoFileClip(file).without_audio().resize((1080, 1920))
        clips.append(clip)
        
    gabungan_video = concatenate_videoclips(clips, method="compose")
    
    if gabungan_video.duration < audio.duration:
        print("[!] Gabungan video lebih pendek dari audio. Melakukan looping...")
        gabungan_video = gabungan_video.fx(vfx.loop, duration=audio.duration)
    else:
        gabungan_video = gabungan_video.subclip(0, audio.duration)
        
    gabungan_video = gabungan_video.set_audio(audio)
    
    try:
        txt_clip = TextClip(
            json_data["judul"], 
            fontsize=45, 
            color='white', 
            bg_color='rgba(0,0,0,0.5)', 
            method='caption', 
            size=(gabungan_video.w - 100, None)
        )
        txt_clip = txt_clip.set_pos(('center', 'center')).set_duration(gabungan_video.duration)
        final_video = CompositeVideoClip([gabungan_video, txt_clip])
    except Exception as e:
        print(f"[!] Gagal membuat teks (ImageMagick error), merender tanpa teks. Error: {e}")
        final_video = gabungan_video
    
    print("[*] Mengekspor hasil akhir (Ini akan memakan waktu)...")
    final_video.write_videofile(
        "hasil_shorts.mp4", 
        fps=24, 
        codec="libx264", 
        audio_codec="aac", 
        threads=2, 
        preset="ultrafast"
    )
    
    print("[*] Membersihkan file sementara...")
    for file in video_files:
        if os.path.exists(file):
            os.remove(file)
    if os.path.exists("audio.mp3"):
        os.remove("audio.mp3")
            
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
        
    with open("token.json", "w") as f:
        f.write(YOUTUBE_TOKEN)
        
    try:
        creds = Credentials.from_authorized_user_file('token.json', ['https://www.googleapis.com/auth/youtube.upload'])
        youtube = build('youtube', 'v3', credentials=creds)
        
        body = {
            'snippet': {
                'title': judul[:100], 
                'description': deskripsi,
                'tags': ['shorts', 'faktaunik', 'negaradunia', 'travel'],
                'categoryId': '22'
            },
            'status': {
                'privacyStatus': 'private', # Default 'private' untuk uji coba (ubah ke 'public' saat sudah siap)
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
        if os.path.exists("token.json"):
            os.remove("token.json")

# ==========================================
# FUNGSI RIWAYAT (HISTORY)
# ==========================================
HISTORY_FILE = "history.txt"

def load_history():
    """Membaca daftar negara yang sudah dibuat videonya."""
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r") as f:
        # Membaca file dan menghapus enter/spasi kosong
        return [line.strip() for line in f.readlines() if line.strip()]

def save_history(negara):
    """Menyimpan negara ke dalam file riwayat."""
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{negara}\n")
    print(f"[*] '{negara}' berhasil dicatat di {HISTORY_FILE}")

# ==========================================
# 7. MAIN FUNCTION (DIPERBARUI)
# ==========================================
async def main():
    # 1. Cek riwayat
    riwayat = load_history()
    negara_tersedia = [n for n in NEGARA_LIST if n not in riwayat]
    
    # 2. Jika semua negara sudah dibahas, kosongkan riwayat agar bot bisa mengulang siklus
    if not negara_tersedia:
        print("[!] Semua negara di daftar telah dibahas. Mereset riwayat...")
        open(HISTORY_FILE, "w").close() # Mengosongkan file
        negara_tersedia = NEGARA_LIST
        
    # 3. Pilih negara dari daftar yang belum pernah dibahas
    negara = random.choice(negara_tersedia)
    print(f"=== MEMULAI BOT UNTUK NEGARA: {negara.upper()} ===")
    
    try:
        # Tahap 1: Generate Konten JSON
        konten = get_script_from_groq(negara)
        print("Data JSON dari Groq:", json.dumps(konten, indent=2))
        
        # Tahap 2: Buat Suara TTS
        await create_voiceover(konten["naskah"])
        
        # Tahap 3: Download 3 Video Berbeda
        downloaded_videos = download_multiple_pexels_videos(konten["query_pexels"])
        
        # Tahap 4: Render Video Final Gabungan
        render_video(konten, downloaded_videos)
        
        # Tahap 5: Upload ke YouTube
        deskripsi_lengkap = f"{konten['deskripsi']}\n\nFootage by Pexels\nScript by Llama-3.3 70B via Groq\nVoice by Edge-TTS\n#shorts"
        upload_to_youtube("hasil_shorts.mp4", konten["judul"], deskripsi_lengkap)
        
        # Tahap 6: Catat ke riwayat HANYA jika upload berhasil
        save_history(negara)
        print("=== SEMUA PROSES BERHASIL SELESAI ===")
        
    except Exception as e:
        print(f"[-] Terjadi kesalahan fatal: {e}")

if __name__ == "__main__":
    asyncio.run(main())
