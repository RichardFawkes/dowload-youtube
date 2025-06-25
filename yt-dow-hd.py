from pytubefix import YouTube
from pytubefix.cli import on_progress
import os
import subprocess
import sys

# URL do vídeo
url = 'https://www.youtube.com/watch?v=uKpGSdIWRqk'

# Cria o objeto YouTube com callback de progresso
yt = YouTube(url, on_progress_callback=on_progress)

print(f"Título: {yt.title}")
print("Resoluções disponíveis:")

# Mostra todas as resoluções disponíveis
all_streams = yt.streams.filter(file_extension='mp4').order_by('resolution').desc()
for stream in all_streams:
    print(f"- {stream.resolution} ({'Progressivo' if stream.is_progressive else 'Adaptativo'}) - {stream.mime_type}")

# Remove caracteres inválidos do nome do arquivo
safe_filename = "".join(c for c in yt.title if c.isalnum() or c in (' ', '-', '_')).rstrip()

# Verifica se ffmpeg está disponível
def check_ffmpeg():
    try:
        # Tenta diferentes caminhos possíveis do FFmpeg
        possible_paths = ['ffmpeg', 'C:\\ffmpeg\\bin\\ffmpeg.exe', 'C:\\Program Files\\FFmpeg\\bin\\ffmpeg.exe']
        for path in possible_paths:
            result = subprocess.run([path, '-version'], capture_output=True, check=True, timeout=10)
            if result.returncode == 0:
                return path
        return None
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None

ffmpeg_path = check_ffmpeg()

if ffmpeg_path:
    print(f"\n✓ FFmpeg encontrado: {ffmpeg_path}")
    print("--- Baixando em ALTA RESOLUÇÃO (1080p) ---")
    
    # Pega o melhor stream de vídeo (1080p)
    video_stream = yt.streams.filter(adaptive=True, file_extension='mp4', only_video=True).order_by('resolution').desc().first()
    
    # Pega o melhor stream de áudio
    audio_stream = yt.streams.filter(adaptive=True, file_extension='mp4', only_audio=True).order_by('abr').desc().first()
    
    if video_stream and audio_stream:
        print(f"📹 Baixando vídeo em {video_stream.resolution}...")
        video_filename = f"{safe_filename}_temp_video.mp4"
        video_stream.download(output_path='.', filename=video_filename)
        
        print(f"🔊 Baixando áudio em {audio_stream.abr}...")
        audio_filename = f"{safe_filename}_temp_audio.mp4"
        audio_stream.download(output_path='.', filename=audio_filename)
        
        # Combina vídeo e áudio
        output_filename = f"{safe_filename}_HD.mp4"
        print("🔄 Combinando vídeo e áudio...")
        
        cmd = [
            ffmpeg_path, 
            '-i', video_filename, 
            '-i', audio_filename,
            '-c:v', 'copy', 
            '-c:a', 'aac', 
            '-y', 
            output_filename
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                # Remove os arquivos temporários
                os.remove(video_filename)
                os.remove(audio_filename)
                print(f"✅ SUCESSO! Download concluído em {video_stream.resolution}")
                print(f"📁 Arquivo salvo como: {output_filename}")
            else:
                print("❌ Erro ao combinar vídeo e áudio:")
                print(result.stderr)
                print("📁 Arquivos separados mantidos:")
                print(f"   - Vídeo: {video_filename}")
                print(f"   - Áudio: {audio_filename}")
        except subprocess.TimeoutExpired:
            print("❌ Timeout ao combinar arquivos. Mantendo arquivos separados.")
    else:
        print("❌ Não foi possível encontrar streams de alta qualidade.")
else:
    print("\n❌ FFmpeg não encontrado.")
    print("💡 Para baixar em 1080p, você precisa:")
    print("   1. Fechar este terminal")
    print("   2. Abrir um NOVO terminal")
    print("   3. Executar este script novamente")
    print("   (O FFmpeg foi instalado mas precisa de um novo terminal)")
    
    print("\n📺 Baixando na melhor qualidade PROGRESSIVA disponível...")
    stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
    if stream:
        print(f"Baixando em {stream.resolution}...")
        stream.download(output_path='.', filename=safe_filename + "_progressivo.mp4")
        print("✅ Download concluído!")
    else:
        print("❌ Nenhum stream disponível.") 