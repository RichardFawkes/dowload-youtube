#!/usr/bin/env python3
"""
Script de teste para verificar se as correções do erro EOF estão funcionando
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_youtube_object
import time

def test_youtube_connection():
    """Testa a conexão com diferentes vídeos do YouTube"""
    
    # URLs de teste (vídeos públicos populares)
    test_urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Rick Roll - sempre disponível
        "https://www.youtube.com/watch?v=kJQP7kiw5Fk",  # Despacito - vídeo popular
        "https://youtu.be/dQw4w9WgXcQ",                  # Formato curto
    ]
    
    print("🧪 Testando correções do erro EOF...")
    print("=" * 60)
    
    for i, url in enumerate(test_urls, 1):
        print(f"\n📺 Teste {i}/{len(test_urls)}: {url}")
        print("-" * 50)
        
        try:
            # Testa criação do objeto YouTube
            yt = create_youtube_object(url)
            
            # Testa acesso às propriedades
            print(f"✅ Título: {yt.title}")
            print(f"✅ Autor: {yt.author}")
            print(f"✅ Duração: {yt.length}s")
            print(f"✅ Views: {yt.views:,}" if yt.views else "✅ Views: N/A")
            
            # Testa streams
            streams = yt.streams.filter(progressive=True, file_extension='mp4')
            print(f"✅ Streams disponíveis: {len(streams)}")
            
            if streams:
                print("📋 Qualidades disponíveis:")
                for stream in streams[:3]:  # Mostra só as 3 primeiras
                    size_mb = f"{stream.filesize / (1024*1024):.1f} MB" if stream.filesize else "N/A"
                    print(f"   • {stream.resolution} - {size_mb}")
            
            print("🎉 SUCESSO: Vídeo processado corretamente!")
            
        except Exception as e:
            error_msg = str(e)
            print(f"❌ ERRO: {error_msg}")
            
            # Analisa o tipo de erro
            if "EOF when reading a line" in error_msg:
                print("🔍 Tipo: Erro EOF - Conexão interrompida")
            elif "Video unavailable" in error_msg:
                print("🔍 Tipo: Vídeo indisponível")
            elif "HTTP Error" in error_msg:
                print("🔍 Tipo: Erro HTTP")
            elif "all strategies failed" in error_msg.lower():
                print("🔍 Tipo: Todas as estratégias falharam")
            else:
                print("🔍 Tipo: Erro desconhecido")
        
        # Pausa entre testes
        if i < len(test_urls):
            print("\n⏳ Aguardando 3 segundos...")
            time.sleep(3)
    
    print("\n" + "=" * 60)
    print("🏁 Testes concluídos!")

def test_error_handling():
    """Testa o tratamento de erros com URLs inválidas"""
    
    print("\n🛠️  Testando tratamento de erros...")
    print("=" * 60)
    
    invalid_urls = [
        "https://www.youtube.com/watch?v=INVALID_VIDEO_ID",
        "https://www.google.com",
        "not_a_url",
        "",
    ]
    
    for i, url in enumerate(invalid_urls, 1):
        print(f"\n❌ Teste {i}/{len(invalid_urls)}: '{url}'")
        print("-" * 30)
        
        try:
            yt = create_youtube_object(url)
            print(f"❓ INESPERADO: URL inválida funcionou - {yt.title}")
        except Exception as e:
            print(f"✅ ESPERADO: Erro capturado - {str(e)[:100]}")

if __name__ == "__main__":
    print("🚀 Iniciando testes das correções EOF...")
    
    try:
        test_youtube_connection()
        test_error_handling()
        
        print("\n✨ Todos os testes concluídos!")
        print("Se você viu mensagens de sucesso, as correções estão funcionando.")
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Testes interrompidos pelo usuário.")
    except Exception as e:
        print(f"\n💥 Erro fatal nos testes: {e}")
        sys.exit(1) 