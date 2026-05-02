import flet as ft
import threading
from core.scraper import TranscriptScraper


def main(page: ft.Page):
    page.title = "Pop the Balloon - Transcript Archiver"
    page.window.width = 1000
    page.window.height = 780
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20

    # ===== ESTADO =====
    output_dir = {"value": None}
    all_videos = []        # lista de dicts vinda do canal
    selected = {}          # idx -> bool  (fonte da verdade de seleção)
    stop_flag = {"value": False}
    kind_filter = {"value": "all"}  # "all", "video", "live"
    mode = {"value": "transcript"}  # "transcript" ou "audio"

    # ===== COMPONENTES =====
    url_field = ft.TextField(
        label="URL do Canal / Vídeo  ou  Nome para Buscar",
        hint_text="Ex: @poptheballoon  |  youtube.com/watch?v=...  |  nome de uma música",
        expand=True,
        height=55,
    )

    folder_text = ft.Text("Nenhuma pasta selecionada", color=ft.colors.GREY_600, size=13)

    search_field = ft.TextField(
        label="Buscar vídeo",
        hint_text="Digite parte do título...",
        expand=True,
        height=48,
        on_change=lambda e: render_list(),
    )

    video_list_view = ft.ListView(expand=True, spacing=0, auto_scroll=False)

    progress_bar = ft.ProgressBar(value=0, width=float("inf"), color=ft.colors.GREEN_600)
    progress_text = ft.Text("", size=12, color=ft.colors.GREY_600)

    log_area = ft.ListView(expand=True, spacing=2, auto_scroll=True)

    count_text = ft.Text("", size=12, color=ft.colors.GREY_700)

    # ===== HELPERS =====
    def append_log(msg):
        log_area.controls.append(ft.Text(msg, size=11, font_family="Courier New", selectable=True))
        page.update()

    def set_progress(current, total):
        progress_bar.value = current / total if total > 0 else 0
        progress_text.value = f"{current}/{total} vídeos processados"
        page.update()

    def visible_indices():
        """Índices dos vídeos que passam no filtro de tipo e de busca."""
        query = search_field.value.strip().lower()
        kf = kind_filter["value"]
        result = []
        for i, v in enumerate(all_videos):
            if kf != "all" and v.get("kind", "video") != kf:
                continue
            if query and query not in v["title"].lower():
                continue
            result.append(i)
        return result

    def update_count():
        n_selected = sum(1 for v in selected.values() if v)
        count_text.value = f"{n_selected} de {len(all_videos)} selecionados"
        page.update()

    def render_list():
        """Reconstrói a lista de vídeos com checkboxes frescos."""
        video_list_view.controls.clear()
        for i in visible_indices():
            idx = i
            cb = ft.Checkbox(
                value=selected.get(idx, False),
                on_change=lambda e, ix=idx: on_cb_change(ix, e.control.value),
            )
            duration = all_videos[idx].get("duration", "")
            row = ft.Container(
                content=ft.Row([
                    cb,
                    ft.Text(
                        all_videos[idx].get("title", "Sem título"),
                        size=12,
                        expand=True,
                        no_wrap=True,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(
                        duration,
                        size=11,
                        color=ft.colors.GREY_600,
                        width=60,
                        text_align=ft.TextAlign.RIGHT,
                    ),
                ]),
                padding=ft.padding.symmetric(horizontal=8, vertical=3),
                border_radius=4,
            )
            video_list_view.controls.append(row)
        n_selected = sum(1 for v in selected.values() if v)
        count_text.value = f"{n_selected} de {len(all_videos)} selecionados"
        page.update()  # um único update no final

    def on_cb_change(idx, value):
        selected[idx] = value
        update_count()

    # ===== SELECIONAR TODOS / NENHUM (só visíveis) =====
    def toggle_all(e):
        vis = visible_indices()
        if not vis:
            return
        all_checked = all(selected.get(i, False) for i in vis)
        new_value = not all_checked
        for i in vis:
            selected[i] = new_value
        render_list()

    # ===== BUSCAR =====
    def fetch_videos(e):
        url = url_field.value.strip()
        if not url:
            page.open(ft.AlertDialog(title=ft.Text("Informe a URL do canal")))
            return

        btn_fetch.disabled = True
        all_videos.clear()
        selected.clear()
        video_list_view.controls.clear()
        search_field.value = ""
        count_text.value = ""
        progress_bar.value = 0
        progress_text.value = ""
        log_area.controls.clear()
        btn_extract.disabled = True
        page.update()

        def _run():
            scraper = TranscriptScraper(output_dir["value"] or ".", append_log)
            kf = kind_filter["value"]

            is_url = url.startswith("http") or "youtube.com" in url or "youtu.be" in url
            import re as _re
            list_match = _re.search(r"list=([\w-]+)", url)
            list_id = list_match.group(1) if list_match else ""
            is_radio = list_id.startswith("RD") or list_id.startswith("RDMM")
            has_playlist = bool(list_id) and not is_radio
            is_single_video = ("watch?v=" in url or "youtu.be/" in url or "/shorts/" in url) and (not has_playlist)

            # Extrai URL limpa da playlist quando a URL mistura vídeo + lista
            def playlist_url(raw):
                import re
                m = re.search(r"list=([\w-]+)", raw)
                if m:
                    list_id = m.group(1)
                    # Playlists de Rádio/Mix (RD...) só funcionam com a URL original
                    if list_id.startswith("RD") or list_id.startswith("RDMM"):
                        return raw
                    return f"https://www.youtube.com/playlist?list={list_id}"
                return raw

            if not is_url:
                items = scraper.search_youtube(url, max_results=20)
                label = "resultado"
            elif has_playlist:
                append_log("Buscando videos da playlist...")
                items = scraper.get_playlist_videos(playlist_url(url))
                label = "vídeo"
            elif is_single_video:
                items = scraper.get_video_info(url)
                label = "vídeo"
            elif kf == "playlist":
                items = scraper.get_channel_playlists(url)
                label = "playlist"
            else:
                append_log("Buscando vídeos do canal...")
                items = scraper.get_playlist_videos(url)
                label = "vídeo"

            if not items:
                append_log(f"Nenhum {label} encontrado. Verifique a entrada.")
                btn_fetch.disabled = False
                page.update()
                return

            for i, video in enumerate(items):
                all_videos.append(video)
                selected[i] = False  # começa tudo desmarcado

            render_list()
            append_log(f"✅ {len(items)} {label}(s) encontrado(s). Selecione os que deseja extrair.")
            btn_fetch.disabled = False
            btn_extract.disabled = False
            page.update()

        threading.Thread(target=_run, daemon=True).start()

    # ===== VERIFICAR DEPENDÊNCIAS =====
    def check_dependencies():
        """Verifica se yt-dlp está disponível (ffmpeg é opcional)."""
        try:
            import subprocess
            from core.scraper import _yt_dlp_cmd
            yt_cmd = _yt_dlp_cmd()

            # Verifica yt-dlp
            result = subprocess.run([yt_cmd, "--version"], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                return False, "yt-dlp não está funcionando"

            # Verifica ffmpeg (opcional, mas recomendado para MP3)
            try:
                result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
                ffmpeg_ok = result.returncode == 0
            except:
                ffmpeg_ok = False

            if not ffmpeg_ok:
                return True, "yt-dlp OK. ffmpeg não encontrado - downloads de áudio podem funcionar em formatos nativos, mas instale ffmpeg para melhor qualidade."

            return True, "Todas as dependências OK"
        except Exception as e:
            return False, f"Erro ao verificar dependências: {e}"

    # ===== EXTRAÇÃO =====
    def start_extraction(e):
        if not output_dir["value"]:
            page.open(ft.AlertDialog(title=ft.Text("Selecione uma pasta de destino")))
            return

        to_extract = [all_videos[i] for i in sorted(selected) if selected[i]]
        if not to_extract:
            page.open(ft.AlertDialog(title=ft.Text("Selecione pelo menos um vídeo")))
            return

        stop_flag["value"] = False
        btn_extract.disabled = True
        btn_stop.disabled = False
        btn_fetch.disabled = True
        log_area.controls.clear()
        progress_bar.value = 0
        page.update()

        def _run():
            scraper = TranscriptScraper(output_dir["value"], append_log)
            success = 0

            # Expande playlists em vídeos individuais
            videos_to_process = []
            for item in to_extract:
                if item.get("kind") == "playlist":
                    append_log(f"📋 Expandindo playlist: {item['title'][:60]}")
                    vids = scraper.get_playlist_videos(item["url"])
                    videos_to_process.extend(vids)
                else:
                    videos_to_process.append(item)

            total = len(videos_to_process)
            action = "Extraindo" if mode["value"] == "transcript" else "Baixando"
            item_type = "vídeos" if mode["value"] == "transcript" else "áudios"
            append_log(f"▶ {action} {total} {item_type}...")

            for idx, video in enumerate(videos_to_process, 1):
                if stop_flag["value"]:
                    append_log("⛔ Processo interrompido.")
                    break
                set_progress(idx, total)

                if mode["value"] == "transcript":
                    # Modo transcrição
                    transcript = scraper.extract_transcript(video["url"], video["title"])
                    if transcript:
                        scraper.save_transcript(video["title"], transcript, video.get("date"))
                        success += 1
                else:
                    # Modo áudio
                    try:
                        append_log(f"Tentando baixar audio: {video['title'][:50]}")
                        if scraper.download_audio(video["url"], video["title"], video.get("date")):
                            success += 1
                            append_log(f"Audio baixado com sucesso: {video['title'][:50]}")
                        else:
                            append_log(f"Falha ao baixar audio: {video['title'][:50]}")
                    except Exception as e:
                        append_log(f"Erro critico no download de audio: {e}")
                        import traceback
                        append_log(f"Traceback: {traceback.format_exc()}")

            append_log(f"\n{'='*50}")
            item_type = "transcrições" if mode["value"] == "transcript" else "áudios"
            append_log(f"Concluído! {success}/{total} {item_type} salvos.")
            append_log(f"Pasta: {output_dir['value']}")
            btn_extract.disabled = False
            btn_stop.disabled = True
            btn_fetch.disabled = False
            progress_text.value = f"Concluído: {success}/{total}"
            page.update()

        threading.Thread(target=_run, daemon=True).start()

    def stop_extraction(e):
        stop_flag["value"] = True
        btn_stop.disabled = True
        append_log("⛔ Parando após o vídeo atual...")
        page.update()

    def pick_folder_result(e: ft.FilePickerResultEvent):
        if e.path:
            output_dir["value"] = e.path
            folder_text.value = e.path
            folder_text.color = ft.colors.GREEN_700
            page.update()

    file_picker = ft.FilePicker(on_result=pick_folder_result)
    page.overlay.append(file_picker)

    def choose_folder(e):
        file_picker.get_directory_path(dialog_title="Escolha a pasta para salvar as transcrições")

    # ===== FILTRO DE TIPO =====
    def set_kind(kind):
        prev = kind_filter["value"]
        kind_filter["value"] = kind
        for k, btn in kind_btns.items():
            btn.style = ft.ButtonStyle(
                bgcolor=ft.colors.BLUE_700 if k == kind else ft.colors.GREY_200,
                color=ft.colors.WHITE if k == kind else ft.colors.GREY_800,
            )
        # Se mudou entre playlists e vídeos, limpa a lista (precisa re-buscar)
        playlist_mode_changed = (prev == "playlist") != (kind == "playlist")
        if playlist_mode_changed and all_videos:
            all_videos.clear()
            selected.clear()
            video_list_view.controls.clear()
            count_text.value = ""
            append_log("ℹ️ Clique em 'Buscar' para carregar os itens deste modo.")
        render_list()

    # ===== SELETOR DE MODO =====
    def set_mode(selected_mode):
        mode["value"] = selected_mode
        for m, btn in mode_btns.items():
            btn.style = ft.ButtonStyle(
                bgcolor=ft.colors.PURPLE_700 if m == selected_mode else ft.colors.GREY_200,
                color=ft.colors.WHITE if m == selected_mode else ft.colors.GREY_800,
            )
        # Atualiza texto do botão principal
        btn_extract.text = "EXTRAIR TRANSCRICOES" if selected_mode == "transcript" else "BAIXAR AUDIOS"
        page.update()

    kind_btns = {
        "all":      ft.ElevatedButton("Todos",      on_click=lambda e: set_kind("all"),      height=36),
        "video":    ft.ElevatedButton("Vídeos",     on_click=lambda e: set_kind("video"),    height=36),
        "live":     ft.ElevatedButton("Lives",      on_click=lambda e: set_kind("live"),     height=36),
        "playlist": ft.ElevatedButton("Playlists",  on_click=lambda e: set_kind("playlist"), height=36),
    }

    mode_btns = {
        "transcript": ft.ElevatedButton("Transcricao", on_click=lambda e: set_mode("transcript"), height=40),
        "audio":      ft.ElevatedButton("Audio",       on_click=lambda e: set_mode("audio"),      height=40),
    }

    set_kind("all")  # aplica estilo inicial dos filtros

    # ===== BOTÕES =====
    btn_fetch = ft.ElevatedButton(
        "🔍 Buscar Vídeos",
        on_click=fetch_videos,
        style=ft.ButtonStyle(bgcolor=ft.colors.BLUE_700, color=ft.colors.WHITE),
        height=50,
        expand=True,
    )

    btn_select_all = ft.OutlinedButton(
        "☑ Sel. Visíveis",
        on_click=toggle_all,
        height=40,
    )

    btn_folder = ft.ElevatedButton(
        "📁 Pasta",
        on_click=choose_folder,
        style=ft.ButtonStyle(bgcolor=ft.colors.ORANGE_600, color=ft.colors.WHITE),
        height=40,
    )

    btn_extract = ft.ElevatedButton(
        "EXTRAIR SELECIONADOS",
        on_click=start_extraction,
        style=ft.ButtonStyle(bgcolor=ft.colors.GREEN_700, color=ft.colors.WHITE),
        height=50,
        expand=True,
        disabled=True,
    )

    btn_stop = ft.ElevatedButton(
        "PARAR",
        on_click=stop_extraction,
        style=ft.ButtonStyle(bgcolor=ft.colors.RED_700, color=ft.colors.WHITE),
        height=50,
        disabled=True,
    )

    set_mode("transcript")  # aplica estilo inicial do modo (btn_extract já existe)

    # ===== LAYOUT =====
    page.add(
        ft.Column(
            controls=[
                ft.Text("Pop the Balloon — Transcript Archiver", size=20, weight=ft.FontWeight.BOLD, color=ft.colors.BLUE_800),
                ft.Divider(height=8),

                ft.Row([url_field, btn_fetch]),
                ft.Row([folder_text, ft.Container(expand=True), btn_folder]),

                ft.Divider(height=8),

                ft.Row([search_field, btn_select_all, count_text]),
                ft.Row([
                    ft.Text("Filtrar:", size=12, color=ft.colors.GREY_700),
                    kind_btns["all"],
                    kind_btns["video"],
                    kind_btns["live"],
                    kind_btns["playlist"],
                ]),

                ft.Container(
                    content=video_list_view,
                    height=280,
                    border=ft.border.all(1, ft.colors.GREY_300),
                    border_radius=6,
                    padding=4,
                ),

                ft.Container(height=6),

                ft.Row([
                    ft.Text("Modo:", size=12, color=ft.colors.GREY_700),
                    mode_btns["transcript"],
                    mode_btns["audio"],
                ]),

                ft.Container(height=4),
                ft.Row([btn_extract, btn_stop]),
                ft.Container(height=4),

                progress_bar,
                progress_text,

                ft.Container(height=4),
                ft.Text("Log", weight=ft.FontWeight.BOLD, size=12),
                ft.Container(
                    content=log_area,
                    height=130,
                    border=ft.border.all(1, ft.colors.GREY_300),
                    border_radius=6,
                    padding=8,
                    bgcolor=ft.colors.GREY_100,
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
