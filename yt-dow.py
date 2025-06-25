from pytubefix import YouTube
from pytubefix.cli import on_progress

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

print("\n--- Tentando baixar na melhor qualidade ---")

# Estratégia 1: Tenta streams progressivos primeiro (mais simples)
stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
if stream and int(stream.resolution.replace('p', '')) >= 720:
    print(f"✓ Encontrado stream progressivo em {stream.resolution}")
    print(f"Baixando: {yt.title} em {stream.resolution}")
    stream.download(output_path='.', filename=safe_filename + ".mp4")
    print("Download concluído!")
else:
    # Estratégia 2: Usa get_highest_resolution (pode não ser progressivo)
    print("Stream progressivo de alta qualidade não disponível.")
    print("Tentando baixar a maior resolução disponível...")
    
    stream = yt.streams.get_highest_resolution()
    if stream:
        print(f"✓ Baixando em {stream.resolution} (pode ser só vídeo ou só áudio)")
        stream.download(output_path='.', filename=safe_filename + "_" + stream.resolution + ".mp4")
        print("Download concluído!")
        
        # Se não for progressivo, tenta baixar áudio separadamente
        if not stream.is_progressive:
            print("Baixando áudio separadamente...")
            audio_stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
            if audio_stream:
                audio_stream.download(output_path='.', filename=safe_filename + "_audio.mp4")
                print("Áudio baixado! Para combinar vídeo e áudio, instale o FFmpeg.")
    else:
        print("❌ Não foi possível encontrar streams de alta qualidade.")
        # Fallback para qualquer stream disponível
        stream = yt.streams.filter(progressive=True, file_extension='mp4').first()
        if stream:
            print(f"Baixando em {stream.resolution} (única opção disponível)")
            stream.download(output_path='.', filename=safe_filename + ".mp4")
            print("Download concluído!")

print("\n📝 Dica: Para baixar sempre em 1080p com vídeo+áudio combinados,")
print("   feche este terminal, abra um novo e execute o script novamente.")
print("   O FFmpeg já foi instalado e estará disponível no novo terminal!")
