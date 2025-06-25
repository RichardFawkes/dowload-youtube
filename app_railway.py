from flask import Flask, render_template, request, jsonify, send_file
from pytubefix import YouTube
from pytubefix.cli import on_progress
import os
import tempfile
import uuid
import threading
import time
import subprocess
import shutil
import random

app = Flask(__name__)

# Configuração para produção
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max

# Diretório para downloads
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), 'downloads')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Status dos downloads
download_status = {}

def create_youtube_object(url):
    """Cria objeto YouTube com configurações anti-bot e múltiplas estratégias"""
    # Lista de user agents para rotação
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15'
    ]
    
    # Estratégias de tentativa (corrigidas)
    strategies = [
        # Estratégia 1: Cliente ANDROID (mais confiável)
        lambda: YouTube(url, client='ANDROID'),
        
        # Estratégia 2: Cliente IOS
        lambda: YouTube(url, client='IOS'),
        
        # Estratégia 3: Cliente WEB padrão
        lambda: YouTube(url, client='WEB'),
        
        # Estratégia 4: Cliente TV_EMBED
        lambda: YouTube(url, client='TV_EMBED'),
        
        # Estratégia 5: Cliente WEB_EMBED
        lambda: YouTube(url, client='WEB_EMBED'),
        
        # Estratégia 6: Com use_po_token
        lambda: YouTube(url, use_po_token=True),
        
        # Estratégia 7: Configuração básica
        lambda: YouTube(url),
        
        # Estratégia 8: Cliente ANDROID com bypass
        lambda: YouTube(url, client='ANDROID_EMBEDDED'),
    ]
    
    # Tenta cada estratégia
    for i, strategy in enumerate(strategies):
        try:
            print(f"Tentando estratégia {i+1}/8...")
            
            # Adiciona delay para evitar rate limiting
            if i > 0:
                time.sleep(random.uniform(1.0, 3.0))
            
            yt = strategy()
            
            # Testa se consegue acessar propriedades básicas
            _ = yt.title  # Força o carregamento dos dados
            _ = yt.length
            
            # Testa se consegue obter streams (importante para evitar 403 no download)
            streams = yt.streams.filter(progressive=True).first()
            if not streams:
                streams = yt.streams.first()
            
            if not streams:
                raise Exception("Nenhum stream disponível")
            
            print(f"✓ Sucesso com estratégia {i+1}")
            return yt
            
        except Exception as e:
            error_msg = str(e)
            print(f"✗ Estratégia {i+1} falhou: {error_msg[:100]}")
            
            # Se é erro 403, tenta estratégias adicionais
            if "403" in error_msg or "Forbidden" in error_msg:
                print("  → Detectado erro 403, aplicando delay adicional...")
                time.sleep(random.uniform(2.0, 5.0))
            
            continue
    
    # Se todas as estratégias falharam
    raise Exception("Todas as estratégias falharam. YouTube pode estar bloqueando o acesso. Tente:\n1. Aguardar alguns minutos\n2. Usar uma VPN\n3. Tentar outro vídeo")

def check_ffmpeg():
    """Verifica se FFmpeg está disponível"""
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def format_duration(seconds):
    """Formata duração em segundos para HH:MM:SS"""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{int(hours):02d}:{int(minutes):02d}:{int(secs):02d}"
    return f"{int(minutes):02d}:{int(secs):02d}"

def format_number(num):
    """Formata números grandes (views)"""
    if num >= 1_000_000:
        return f"{num/1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num/1_000:.1f}K"
    return str(num)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_video_info', methods=['POST'])
def get_video_info():
    """Obtém informações do vídeo"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'URL é obrigatória'}), 400
        
        # Validação básica da URL
        if 'youtube.com' not in url and 'youtu.be' not in url:
            return jsonify({'error': 'URL deve ser do YouTube'}), 400
        
        print(f"Processando URL: {url}")
        
        # Cria objeto YouTube com anti-bot e múltiplas estratégias
        yt = create_youtube_object(url)
        
        print("✓ Objeto YouTube criado com sucesso")
        
        # Obtém informações básicas com tratamento de erro individual
        try:
            title = yt.title
            print(f"✓ Título obtido: {title[:50]}...")
        except Exception as e:
            print(f"✗ Erro ao obter título: {e}")
            title = "Título não disponível"
        
        try:
            author = yt.author
            print(f"✓ Autor obtido: {author}")
        except Exception as e:
            print(f"✗ Erro ao obter autor: {e}")
            author = "Autor não disponível"
        
        try:
            length = yt.length
            print(f"✓ Duração obtida: {length}s")
        except Exception as e:
            print(f"✗ Erro ao obter duração: {e}")
            length = 0
        
        try:
            thumbnail = yt.thumbnail_url
            print("✓ Thumbnail obtida")
        except Exception as e:
            print(f"✗ Erro ao obter thumbnail: {e}")
            thumbnail = ""
        
        try:
            views = yt.views or 0
            print(f"✓ Views obtidas: {views}")
        except Exception as e:
            print(f"✗ Erro ao obter views: {e}")
            views = 0
        
        try:
            description = yt.description or ""
            print("✓ Descrição obtida")
        except Exception as e:
            print(f"✗ Erro ao obter descrição: {e}")
            description = ""
        
        # Obtém informações básicas
        video_info = {
            'title': title,
            'author': author,
            'length': length,
            'thumbnail': thumbnail,
            'views': views,
            'description': description[:200] + '...' if len(description) > 200 else description
        }
        
        print("✓ Informações básicas coletadas")
        
        # Verifica se FFmpeg está disponível
        ffmpeg_available = check_ffmpeg()
        print(f"FFmpeg disponível: {ffmpeg_available}")
        
        # Obtém streams disponíveis
        streams = []
        
        try:
            if ffmpeg_available:
                # Com FFmpeg: streams adaptivos (HD)
                print("Buscando streams adaptivos...")
                video_streams = yt.streams.filter(adaptive=True, file_extension='mp4', only_video=True).order_by('resolution').desc()
                for stream in video_streams:
                    if stream.resolution in ['1080p', '720p', '480p', '360p']:
                        streams.append({
                            'resolution': stream.resolution,
                            'type': 'adaptive',
                            'size': f"{stream.filesize / (1024*1024):.1f} MB" if stream.filesize else 'N/A',
                            'quality': f"{stream.resolution} HD (Vídeo + Áudio)"
                        })
                print(f"✓ {len([s for s in streams if s['type'] == 'adaptive'])} streams adaptivos encontrados")
            
            # Streams progressivos (funcionam sem FFmpeg)
            print("Buscando streams progressivos...")
            progressive_streams = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc()
            for stream in progressive_streams:
                if stream.resolution:  # Só adiciona se tem resolução válida
                    streams.append({
                        'resolution': stream.resolution,
                        'type': 'progressive',
                        'size': f"{stream.filesize / (1024*1024):.1f} MB" if stream.filesize else 'N/A',
                        'quality': f"{stream.resolution} (Vídeo + Áudio)"
                    })
            print(f"✓ {len([s for s in streams if s['type'] == 'progressive'])} streams progressivos encontrados")
            
            # Stream de áudio apenas
            print("Buscando stream de áudio...")
            audio_stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
            if audio_stream:
                streams.append({
                    'resolution': 'audio',
                    'type': 'audio',
                    'size': f"{audio_stream.filesize / (1024*1024):.1f} MB" if audio_stream.filesize else 'N/A',
                    'quality': f"Apenas Áudio ({audio_stream.abr})"
                })
                print("✓ Stream de áudio encontrado")
            
        except Exception as e:
            print(f"✗ Erro ao obter streams: {e}")
            # Fallback: pelo menos tenta obter um stream básico
            try:
                basic_stream = yt.streams.first()
                if basic_stream:
                    streams.append({
                        'resolution': '360p',
                        'type': 'basic',
                        'size': 'N/A',
                        'quality': 'Qualidade Básica'
                    })
            except:
                pass
        
        if not streams:
            return jsonify({'error': 'Nenhum stream disponível para este vídeo'}), 400
        
        print(f"✓ Total de {len(streams)} streams disponíveis")
        
        return jsonify({
            'video_info': video_info,
            'streams': streams,
            'ffmpeg_available': ffmpeg_available
        })
        
    except Exception as e:
        error_message = str(e)
        print(f"✗ Erro geral: {error_message}")
        
        # Mensagens de erro mais informativas
        if "EOF when reading a line" in error_message:
            error_message = "Erro de conexão com YouTube. Tente novamente em alguns minutos."
        elif "Video unavailable" in error_message:
            error_message = "Vídeo não disponível ou privado."
        elif "regex_search" in error_message:
            error_message = "Erro ao processar dados do YouTube. Pode ser um problema temporário."
        elif "HTTP Error 429" in error_message:
            error_message = "Muitas requisições. Aguarde alguns minutos antes de tentar novamente."
        elif "all strategies failed" in error_message.lower():
            error_message = "YouTube está bloqueando o acesso. Tente novamente em alguns minutos ou use uma VPN."
        
        return jsonify({'error': f'Erro ao obter informações do vídeo: {error_message}'}), 400

@app.route('/start_download', methods=['POST'])
def start_download():
    """Inicia o download do vídeo"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        resolution = data.get('resolution', '').strip()
        
        if not url or not resolution:
            return jsonify({'error': 'URL e resolução são obrigatórias'}), 400
        
        # Gera ID único para o download
        download_id = str(uuid.uuid4())
        
        # Inicializa status
        download_status[download_id] = {
            'status': 'starting',
            'progress': 0,
            'filename': '',
            'error': None
        }
        
        # Inicia download em thread separada
        thread = threading.Thread(
            target=download_video_thread,
            args=(download_id, url, resolution)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({'download_id': download_id})
        
    except Exception as e:
        return jsonify({'error': f'Erro ao iniciar download: {str(e)}'}), 400

def download_video_thread(download_id, url, resolution):
    """Thread para download do vídeo"""
    try:
        # Atualiza status
        download_status[download_id]['status'] = 'downloading'
        
        # Cria objeto YouTube com anti-bot - com retry para 403
        retry_count = 3
        yt = None
        
        for attempt in range(retry_count):
            try:
                yt = create_youtube_object(url)
                break
            except Exception as e:
                if "403" in str(e) or "Forbidden" in str(e):
                    if attempt < retry_count - 1:
                        print(f"Tentativa {attempt + 1} falhou com 403, tentando novamente em 5s...")
                        time.sleep(5)
                        continue
                    else:
                        raise Exception(f"Erro 403 persistente após {retry_count} tentativas. YouTube pode estar bloqueando o acesso.")
                else:
                    raise e
        
        if not yt:
            raise Exception("Não foi possível criar objeto YouTube")
        
        # Nome seguro do arquivo
        safe_filename = "".join(c for c in yt.title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        
        if resolution == 'audio':
            # Download apenas áudio
            print("Baixando stream de áudio...")
            stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
            if not stream:
                raise Exception("Stream de áudio não encontrado")
            
            filename = f"{safe_filename}_audio.mp4"
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            
            # Download com retry para 403
            for attempt in range(3):
                try:
                    stream.download(output_path=DOWNLOAD_DIR, filename=filename)
                    break
                except Exception as e:
                    if "403" in str(e) and attempt < 2:
                        print(f"Erro 403 no download de áudio, tentativa {attempt + 1}/3")
                        time.sleep(3)
                        continue
                    else:
                        raise e
            
        elif resolution in ['1080p', '720p'] and check_ffmpeg():
            # Download HD com FFmpeg
            print(f"Baixando stream HD {resolution}...")
            
            # Busca streams com retry
            video_stream = None
            audio_stream = None
            
            for attempt in range(3):
                try:
                    video_stream = yt.streams.filter(adaptive=True, file_extension='mp4', res=resolution, only_video=True).first()
                    audio_stream = yt.streams.filter(adaptive=True, file_extension='mp4', only_audio=True).order_by('abr').desc().first()
                    break
                except Exception as e:
                    if "403" in str(e) and attempt < 2:
                        print(f"Erro 403 ao buscar streams, tentativa {attempt + 1}/3")
                        time.sleep(3)
                        # Recria objeto YouTube
                        yt = create_youtube_object(url)
                        continue
                    else:
                        raise e
            
            if not video_stream or not audio_stream:
                raise Exception(f"Stream {resolution} não encontrado após múltiplas tentativas")
            
            # Arquivos temporários
            video_temp = os.path.join(DOWNLOAD_DIR, f"temp_video_{download_id}.mp4")
            audio_temp = os.path.join(DOWNLOAD_DIR, f"temp_audio_{download_id}.mp4")
            
            # Download streams com retry
            download_status[download_id]['status'] = 'downloading_video'
            for attempt in range(3):
                try:
                    video_stream.download(output_path=DOWNLOAD_DIR, filename=f"temp_video_{download_id}.mp4")
                    break
                except Exception as e:
                    if "403" in str(e) and attempt < 2:
                        print(f"Erro 403 no download de vídeo, tentativa {attempt + 1}/3")
                        time.sleep(5)
                        continue
                    else:
                        raise e
            
            download_status[download_id]['status'] = 'downloading_audio'
            for attempt in range(3):
                try:
                    audio_stream.download(output_path=DOWNLOAD_DIR, filename=f"temp_audio_{download_id}.mp4")
                    break
                except Exception as e:
                    if "403" in str(e) and attempt < 2:
                        print(f"Erro 403 no download de áudio, tentativa {attempt + 1}/3")
                        time.sleep(5)
                        continue
                    else:
                        raise e
            
            # Combina com FFmpeg
            download_status[download_id]['status'] = 'processing'
            filename = f"{safe_filename}_{resolution}.mp4"
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            
            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-i', video_temp,
                '-i', audio_temp,
                '-c', 'copy',
                filepath
            ]
            
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True)
            
            # Remove arquivos temporários
            if os.path.exists(video_temp):
                os.remove(video_temp)
            if os.path.exists(audio_temp):
                os.remove(audio_temp)
            
        else:
            # Download progressivo
            print(f"Baixando stream progressivo {resolution}...")
            
            # Busca stream com fallback
            stream = yt.streams.filter(progressive=True, file_extension='mp4', res=resolution).first()
            if not stream:
                # Fallback para qualquer stream progressivo
                stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
                if not stream:
                    raise Exception(f"Nenhum stream progressivo disponível")
            
            filename = f"{safe_filename}_{stream.resolution}.mp4"
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            
            # Download com retry para 403
            for attempt in range(3):
                try:
                    stream.download(output_path=DOWNLOAD_DIR, filename=filename)
                    break
                except Exception as e:
                    if "403" in str(e) and attempt < 2:
                        print(f"Erro 403 no download progressivo, tentativa {attempt + 1}/3")
                        time.sleep(5)
                        # Tenta recriar o objeto YouTube
                        yt = create_youtube_object(url)
                        stream = yt.streams.filter(progressive=True, file_extension='mp4', res=resolution).first()
                        if not stream:
                            stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
                        continue
                    else:
                        raise e
        
        # Sucesso
        download_status[download_id].update({
            'status': 'completed',
            'progress': 100,
            'filename': filename,
            'filepath': filepath
        })
        
        print(f"✓ Download concluído: {filename}")
        
    except Exception as e:
        error_msg = str(e)
        print(f"✗ Erro no download: {error_msg}")
        
        # Mensagens de erro mais informativas
        if "403" in error_msg or "Forbidden" in error_msg:
            error_msg = "YouTube está bloqueando o download. Tente aguardar alguns minutos ou usar uma VPN."
        elif "404" in error_msg:
            error_msg = "Vídeo não encontrado ou foi removido."
        elif "regex_search" in error_msg:
            error_msg = "Erro ao processar dados do YouTube. Pode ser um problema temporário."
        
        download_status[download_id].update({
            'status': 'error',
            'error': error_msg
        })

@app.route('/download_status/<download_id>')
def get_download_status(download_id):
    """Retorna status do download"""
    if download_id not in download_status:
        return jsonify({'error': 'Download não encontrado'}), 404
    
    return jsonify(download_status[download_id])

@app.route('/download_file/<download_id>')
def download_file(download_id):
    """Faz download do arquivo"""
    if download_id not in download_status:
        return jsonify({'error': 'Download não encontrado'}), 404
    
    status = download_status[download_id]
    if status['status'] != 'completed':
        return jsonify({'error': 'Download não concluído'}), 400
    
    filepath = status['filepath']
    if not os.path.exists(filepath):
        return jsonify({'error': 'Arquivo não encontrado'}), 404
    
    return send_file(filepath, as_attachment=True, download_name=status['filename'])

# Limpeza automática de arquivos antigos (executar periodicamente)
def cleanup_old_files():
    """Remove arquivos antigos"""
    try:
        current_time = time.time()
        for filename in os.listdir(DOWNLOAD_DIR):
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.isfile(filepath):
                # Remove arquivos com mais de 1 hora
                if current_time - os.path.getmtime(filepath) > 3600:
                    os.remove(filepath)
    except Exception as e:
        print(f"Erro na limpeza: {e}")

# Executar limpeza a cada 30 minutos
def schedule_cleanup():
    while True:
        time.sleep(1800)  # 30 minutos
        cleanup_old_files()

# Inicia thread de limpeza
cleanup_thread = threading.Thread(target=schedule_cleanup)
cleanup_thread.daemon = True
cleanup_thread.start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False) 