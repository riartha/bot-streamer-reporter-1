import discord
from discord.ext import tasks
import gspread
from gspread.exceptions import WorksheetNotFound
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pytz
import re
import asyncio
import sys

# ==========================================
# KONFIGURASI GOOGLE SHEETS
# ==========================================
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDENTIALS_FILE = "credentials.json"
SPREADSHEET_ID = ""

SHEET_NAME_ABSEN = "Sheet Absensi Only (Test)"
SHEET_NAME_REWARD = "Sheet Reward Streamer"
SHEET_NAME_KUPON = "Sheet Kupon Streamer" 


# ==========================================
# KONFIGURASI BOT DISCORD
# ==========================================
TOKEN = ''

DEDICATED_CHANNEL_ID_ABSEN =   # Ganti ID Channel Absen
DEDICATED_CHANNEL_ID_REWARD =  # Ganti ID Channel Reward
DEDICATED_CHANNEL_ID_KUPON =   # Ganti ID Channel Kupon
BOT_NAME = "Blaze Streamer Bot"
USER_MODE = "1" 

# Variabel Global untuk Fitur 4 (Inputan User)
CUSTOM_CHANNEL_ID = None
CUSTOM_SHEET_NAME = None

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# ==========================================
# FUNGSI PENDUKUNG
# ==========================================
def connect_gsheet_client():
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPE)
    return gspread.authorize(creds)

def connect_gsheet(sheet_name):
    gc = connect_gsheet_client()
    return gc.open_by_key(SPREADSHEET_ID).worksheet(sheet_name)

def format_tanggal(dt):
    hari_indo = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
    bulan_indo = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    return f"{hari_indo[dt.weekday()]}, {dt.day:02d} {bulan_indo[dt.month - 1]} {dt.year}"

# Format Auto-Styling untuk Fitur 4 (Warna Ungu & Font Calibri)
def apply_custom_sheet_formatting(sheet):
    # 1. Tulis Teks Header
    sheet.update_cell(1, 1, 'ID Discord')
    sheet.update_cell(1, 2, 'Display Name')
    sheet.update_cell(1, 3, 'Isi Chat')
    
    # 2. Format Header A1:C1 (Warna Ungu, Putih, Center, Bold, Calibri 12)
    sheet.format("A1:C1", {
        "backgroundColor": {
            "red": 103.0 / 255.0,   # Hex 67
            "green": 78.0 / 255.0,  # Hex 4e
            "blue": 167.0 / 255.0   # Hex a7
        },
        "textFormat": {
            "foregroundColor": {
                "red": 1.0,
                "green": 1.0,
                "blue": 1.0
            },
            "fontFamily": "Calibri",
            "fontSize": 12,
            "bold": True
        },
        "horizontalAlignment": "CENTER"
    })
    
    # 3. Format Data Body A2:C1000 (Calibri 11)
    sheet.format("A2:C1000", {
        "textFormat": {
            "fontFamily": "Calibri",
            "fontSize": 11
        }
    })

# Format Chat
def format_append_chat_absen(existing_text, new_chat):
    if not existing_text or str(existing_text).strip() == "": return f"[1] {new_chat}"
    existing_str = str(existing_text).strip()
    matches = re.findall(r'\[(\d+)\]', existing_str)
    next_num = max(int(m) for m in matches) + 1 if matches else 2
    return f"{existing_str}\n[{next_num}] {new_chat}"

def is_chat_recorded_absen(existing_text, new_chat):
    if not existing_text or str(existing_text).strip() == "": return False
    recorded_chats = re.split(r'\[\d+\]\s*', str(existing_text))
    new_chat_norm = " ".join(new_chat.strip().split())
    recorded_chats_norm = [" ".join(chat.strip().split()) for chat in recorded_chats if chat.strip()]
    return new_chat_norm in recorded_chats_norm

def format_append_chat_with_date(existing_text, new_chat, dt):
    tanggal_jam = dt.strftime('%d %B %Y, %H:%M')
    formatted_new_chat = f"{tanggal_jam} | {new_chat}"
    if not existing_text or str(existing_text).strip() == "": return f"[1] {formatted_new_chat}"
    existing_str = str(existing_text).strip()
    matches = re.findall(r'\[(\d+)\]', existing_str)
    next_num = max(int(m) for m in matches) + 1 if matches else 2
    return f"{existing_str}\n[{next_num}] {formatted_new_chat}"

def is_chat_recorded_with_date(existing_text, new_chat):
    if not existing_text or str(existing_text).strip() == "": return False
    new_chat_norm = " ".join(new_chat.strip().split())
    existing_norm = " ".join(str(existing_text).strip().split())
    return new_chat_norm in existing_norm

def generate_kupon_summary(full_chat_text):
    if not full_chat_text or str(full_chat_text).strip() == "": return ""
    raw_chats = re.split(r'\[\d+\] \d{2} [a-zA-Z]+ \d{4}, \d{2}:\d{2} \| ', str(full_chat_text))
    counts = {}
    for chat in raw_chats:
        chat = chat.strip()
        if not chat: continue
        match = re.search(r'(?i)nick\s*:\s*([^\n]+)', chat)
        if match:
            nick_val = match.group(1).strip()
            counts[nick_val] = counts.get(nick_val, 0) + 1
        else:
            counts["<unidentified>"] = counts.get("<unidentified>", 0) + 1
    return "\n".join([f"{n} : {j}x" for n, j in counts.items()])

# ==========================================
# FUNGSI SCANNER ABSEN (FITUR 1)
# ==========================================
async def scan_absen_live():
    tz = pytz.timezone('Asia/Jakarta')
    print(f"\n[{datetime.now(tz).strftime('%H:%M:%S')}] --- [FITUR 1] SCANNING ABSEN LIVE ---")
    channel = client.get_channel(DEDICATED_CHANNEL_ID_ABSEN)
    if not channel:
        print("Error: Channel Absen Live tidak ditemukan!")
        return
    try:
        sheet = connect_gsheet(SHEET_NAME_ABSEN)
        all_values = sheet.get_all_values()
        if not all_values or len(all_values) < 2: return
        col_a_values = [row[0] if len(row) > 0 else "" for row in all_values]
        row_2_values = all_values[1]
        rekap_hasil = {}
        messages = [msg async for msg in channel.history(limit=2000)]
        messages.reverse() 
        for msg in messages:
            if msg.author == client.user or not msg.content.strip(): continue
            waktu_pesan_wib = msg.created_at.astimezone(tz)
            tanggal_pesan = format_tanggal(waktu_pesan_wib)
            discord_id = str(msg.author.name) 
            try: row_target = col_a_values.index(discord_id) + 1
            except ValueError: continue
            try: col_target = row_2_values.index(tanggal_pesan) + 1
            except ValueError: continue
            current_val = ""
            if len(all_values) >= row_target and len(all_values[row_target - 1]) >= col_target:
                current_val = all_values[row_target - 1][col_target - 1]
            if is_chat_recorded_absen(current_val, msg.content): continue 
            updated_text = format_append_chat_absen(current_val, msg.content)
            try:
                sheet.update_cell(row_target, col_target, updated_text)
                while len(all_values) < row_target: all_values.append([])
                while len(all_values[row_target - 1]) < col_target: all_values[row_target - 1].append("")
                all_values[row_target - 1][col_target - 1] = updated_text
                rekap_hasil[tanggal_pesan] = rekap_hasil.get(tanggal_pesan, 0) + 1
                await asyncio.sleep(2.0)
            except Exception:
                await asyncio.sleep(5.0) 
        if rekap_hasil: print(f"-> Selesai! Terekam absen baru: {rekap_hasil}")
        else: print("-> Selesai Scan Absen. (Semua sinkron).")
    except Exception as e: print(f"Error Fitur Absen: {e}")

# ==========================================
# FUNGSI SCANNER REWARD (FITUR 2)
# ==========================================
async def scan_reward_streamer():
    tz = pytz.timezone('Asia/Jakarta')
    print(f"\n[{datetime.now(tz).strftime('%H:%M:%S')}] --- [FITUR 2] SCANNING REWARD STREAMER ---")
    channel = client.get_channel(DEDICATED_CHANNEL_ID_REWARD)
    if not channel: return
    try:
        sheet = connect_gsheet(SHEET_NAME_REWARD)
        all_values = sheet.get_all_values()
        col_a_values = [str(row[0]).strip() if len(row) > 0 else "" for row in all_values]
        messages = [msg async for msg in channel.history(limit=2000)]
        messages.reverse()
        added_users = recorded_chats = 0
        for msg in messages:
            if msg.author == client.user or not msg.content.strip(): continue
            author_id = str(msg.author.name) 
            author_name = str(msg.author.display_name) or "<username_manual>"
            waktu_pesan_wib = msg.created_at.astimezone(tz)
            if author_id not in col_a_values:
                chat_awal = format_append_chat_with_date("", msg.content, waktu_pesan_wib)
                try: new_row_number = col_a_values.index("") + 1
                except ValueError: new_row_number = len(col_a_values) + 1
                try:
                    sheet.update_cell(new_row_number, 1, author_id)
                    sheet.update_cell(new_row_number, 2, author_name)
                    sheet.update_cell(new_row_number, 4, "√")
                    sheet.update_cell(new_row_number, 5, chat_awal)
                    while len(all_values) < new_row_number: all_values.append([])
                    while len(all_values[new_row_number - 1]) < 5: all_values[new_row_number - 1].append("")
                    all_values[new_row_number - 1][0] = author_id
                    all_values[new_row_number - 1][1] = author_name
                    all_values[new_row_number - 1][3] = "√"
                    all_values[new_row_number - 1][4] = chat_awal
                    col_a_values = [str(row[0]).strip() if len(row) > 0 else "" for row in all_values]
                    added_users += 1; recorded_chats += 1
                    await asyncio.sleep(2.0) 
                except Exception: await asyncio.sleep(5.0)
                continue
            row_target = col_a_values.index(author_id) + 1
            while len(all_values[row_target - 1]) < 5: all_values[row_target - 1].append("")
            current_chat = all_values[row_target - 1][4]   
            if is_chat_recorded_with_date(current_chat, msg.content): continue
            updated_chat = format_append_chat_with_date(current_chat, msg.content, waktu_pesan_wib)
            try:
                sheet.update_cell(row_target, 4, "√")
                sheet.update_cell(row_target, 5, updated_chat)
                all_values[row_target - 1][3] = "√"
                all_values[row_target - 1][4] = updated_chat
                recorded_chats += 1
                await asyncio.sleep(2.0)
            except Exception: await asyncio.sleep(5.0)
        for i in range(1, len(all_values)): 
            while len(all_values[i]) < 5: all_values[i].append("")
            status, chat_log = all_values[i][3], all_values[i][4]
            if str(all_values[i][0]).strip() != "" and (not chat_log or str(chat_log).strip() == "") and status != "×":
                try:
                    sheet.update_cell(i + 1, 4, "×")
                    all_values[i][3] = "×"
                    await asyncio.sleep(2.0)
                except Exception: pass
        print(f"-> Selesai! User Baru: {added_users} | Chat Direkam: {recorded_chats}")
    except Exception as e: print(f"Error Fitur Reward: {e}")

# ==========================================
# FUNGSI SCANNER KUPON (FITUR 3)
# ==========================================
async def scan_kupon_streamer():
    tz = pytz.timezone('Asia/Jakarta')
    print(f"\n[{datetime.now(tz).strftime('%H:%M:%S')}] --- [FITUR 3] SCANNING KUPON STREAMER ---")
    channel = client.get_channel(DEDICATED_CHANNEL_ID_KUPON)
    if not channel: return
    try:
        sheet = connect_gsheet(SHEET_NAME_KUPON)
        all_values = sheet.get_all_values()
        col_a_values = [str(row[0]).strip() if len(row) > 0 else "" for row in all_values]
        messages = [msg async for msg in channel.history(limit=2000)]
        messages.reverse()
        added_users = recorded_chats = 0
        for msg in messages:
            if msg.author == client.user or not msg.content.strip(): continue
            author_id = str(msg.author.name)
            author_name = str(msg.author.display_name) or "<username_manual>"
            waktu_pesan_wib = msg.created_at.astimezone(tz)
            if author_id not in col_a_values:
                chat_awal = format_append_chat_with_date("", msg.content, waktu_pesan_wib)
                summary_awal = generate_kupon_summary(chat_awal)
                try: new_row_number = col_a_values.index("") + 1
                except ValueError: new_row_number = len(col_a_values) + 1
                try:
                    sheet.update_cell(new_row_number, 1, author_id) 
                    sheet.update_cell(new_row_number, 2, author_name) 
                    sheet.update_cell(new_row_number, 4, chat_awal) 
                    sheet.update_cell(new_row_number, 5, summary_awal)
                    while len(all_values) < new_row_number: all_values.append([])
                    while len(all_values[new_row_number - 1]) < 5: all_values[new_row_number - 1].append("")
                    all_values[new_row_number - 1][0] = author_id
                    all_values[new_row_number - 1][1] = author_name
                    all_values[new_row_number - 1][3] = chat_awal
                    all_values[new_row_number - 1][4] = summary_awal
                    col_a_values = [str(row[0]).strip() if len(row) > 0 else "" for row in all_values]
                    added_users += 1; recorded_chats += 1
                    await asyncio.sleep(2.0) 
                except Exception: await asyncio.sleep(5.0)
                continue
            row_target = col_a_values.index(author_id) + 1
            while len(all_values[row_target - 1]) < 5: all_values[row_target - 1].append("")
            current_chat = all_values[row_target - 1][3] 
            if is_chat_recorded_with_date(current_chat, msg.content): continue
            updated_chat = format_append_chat_with_date(current_chat, msg.content, waktu_pesan_wib)
            updated_summary = generate_kupon_summary(updated_chat)
            try:
                sheet.update_cell(row_target, 4, updated_chat)
                sheet.update_cell(row_target, 5, updated_summary)
                all_values[row_target - 1][3] = updated_chat
                all_values[row_target - 1][4] = updated_summary
                recorded_chats += 1
                await asyncio.sleep(2.0)
            except Exception: await asyncio.sleep(5.0)
        print(f"-> Selesai! User Baru: {added_users} | Chat Direkam: {recorded_chats}")
    except Exception as e: print(f"Error Fitur Kupon: {e}")

# ==========================================
# FUNGSI SCANNER CUSTOM (FITUR 4)
# ==========================================
async def scan_custom_channel():
    tz = pytz.timezone('Asia/Jakarta')
    print(f"\n[{datetime.now(tz).strftime('%H:%M:%S')}] --- [FITUR 4] SCANNING CUSTOM CHANNEL (OPTIMIZED) ---")

    channel = client.get_channel(int(CUSTOM_CHANNEL_ID))
    if not channel:
        print(f"Error: Channel Custom dengan ID {CUSTOM_CHANNEL_ID} tidak ditemukan!")
        return

    try:
        gc = connect_gsheet_client()
        spreadsheet = gc.open_by_key(SPREADSHEET_ID)

        target_sheet_name = CUSTOM_SHEET_NAME
        try:
            sheet = spreadsheet.worksheet(target_sheet_name)
            headers = sheet.row_values(1)

            while len(headers) < 3:
                headers.append("")

            if headers[0] == 'ID Discord' and headers[1] == 'Display Name' and headers[2] == 'Isi Chat':
                print(f"-> Sheet '{target_sheet_name}' ditemukan dan format valid. Bot akan mengupdate data.")
            else:
                target_sheet_name = f"{CUSTOM_SHEET_NAME} (BOT)"
                print(f"-> Format header berbeda! Bot beralih ke sheet: '{target_sheet_name}'")
                try:
                    sheet = spreadsheet.worksheet(target_sheet_name)
                    print(f"-> Menggunakan sheet '{target_sheet_name}' yang sudah ada.")
                except WorksheetNotFound:
                    print(f"-> Membuat sheet baru '{target_sheet_name}' beserta format warnanya...")
                    sheet = spreadsheet.add_worksheet(title=target_sheet_name, rows=1000, cols=10)
                    apply_custom_sheet_formatting(sheet)

        except WorksheetNotFound:
            print(f"-> Sheet '{target_sheet_name}' tidak ditemukan. Bot membuat sheet baru...")
            sheet = spreadsheet.add_worksheet(title=target_sheet_name, rows=1000, cols=10)
            apply_custom_sheet_formatting(sheet)

        # 1. Ambil seluruh data sheet sekaligus ke memori lokal
        all_values = sheet.get_all_values()

        # Pastikan minimal ada baris header
        if not all_values:
            apply_custom_sheet_formatting(sheet)
            all_values = sheet.get_all_values()

        # Mapping Discord ID ke indeks baris (0-indexed dalam list)
        # Baris 0 adalah Header ('ID Discord', 'Display Name', 'Isi Chat')
        col_a_map = {}
        for idx, row in enumerate(all_values):
            if idx == 0: continue  # Skip header
            id_val = str(row[0]).strip() if len(row) > 0 else ""
            if id_val:
                col_a_map[id_val] = idx

        print("-> Menarik riwayat chat dari Discord (Mohon tunggu)...")
        messages = [msg async for msg in channel.history(limit=2000)]
        messages.reverse()
        print(f"-> Berhasil menarik {len(messages)} pesan. Mulai mencocokkan data...")

        added_users = 0
        recorded_chats = 0
        is_dirty = False  # Penanda jika ada perubahan data

        # 2. Proses pesan secara in-memory
        for msg in messages:
            if msg.author == client.user or not msg.content.strip():
                continue

            author_id = str(msg.author.name)
            author_name = str(msg.author.display_name)
            if not author_name or author_name.strip() == "":
                author_name = "<username_manual>"

            waktu_pesan_wib = msg.created_at.astimezone(tz)

            if author_id not in col_a_map:
                # User baru: Tambahkan baris baru di memori
                chat_awal = format_append_chat_with_date("", msg.content, waktu_pesan_wib)
                new_row = [author_id, author_name, chat_awal]

                all_values.append(new_row)
                col_a_map[author_id] = len(all_values) - 1

                added_users += 1
                recorded_chats += 1
                is_dirty = True
            else:
                # User lama: Update chat di memori jika belum terekam
                row_idx = col_a_map[author_id]

                # Pastikan panjang elemen array minimal 3
                while len(all_values[row_idx]) < 3:
                    all_values[row_idx].append("")

                current_chat = all_values[row_idx][2]
                if is_chat_recorded_with_date(current_chat, msg.content):
                    continue

                updated_chat = format_append_chat_with_date(current_chat, msg.content, waktu_pesan_wib)
                all_values[row_idx][2] = updated_chat
                recorded_chats += 1
                is_dirty = True

        # 3. Kirim update sekaligus ke Google Sheets dalam 1 request jika ada perubahan
        if is_dirty:
            print("-> Mengunggah perubahan ke Google Sheets...")
            sheet.update(range_name=f'A1:C{len(all_values)}', values=all_values)
            print(f"-> Selesai! User Baru: {added_users} | Chat Direkam: {recorded_chats}")
        else:
            print("-> Selesai! Tidak ada data/chat baru yang perlu diupdate (Sudah sinkron).")

    except Exception as e:
        print(f"Error Fatal di Fitur Custom: {e}")
                
        print(f"-> Selesai! User Baru: {added_users} | Chat Direkam: {recorded_chats}")
    except Exception as e:
        print(f"Error Fatal di Fitur Custom: {e}")

# ==========================================
# MASTER SCHEDULER
# ==========================================
@tasks.loop(hours=1)
async def master_scanner():
    if USER_MODE in ["1", "5"]:
        await scan_absen_live()
    if USER_MODE in ["2", "5"]:
        await scan_reward_streamer()
    if USER_MODE in ["3", "5"]:
        await scan_kupon_streamer()
    if USER_MODE == "4":
        await scan_custom_channel()
        
    print("\n=========================================")
    tz = pytz.timezone('Asia/Jakarta')
    print(f"[{datetime.now(tz).strftime('%H:%M:%S')}] Siklus Semua Scanning Selesai.")
    print("Menunggu 1 jam berikutnya...")
    print("=========================================\n")

# ==========================================
# EVENT DISCORD
# ==========================================
@client.event
async def on_ready():
    print(f'\n[SUCCESS] Login berhasil sebagai {client.user}')
    print(f"Mode Terpilih: Fitur {USER_MODE}")
    if not master_scanner.is_running():
        master_scanner.start()

# ==========================================
# MAIN MENU (CLI COMMAND PROMPT)
# ==========================================
def main():
    global USER_MODE, CUSTOM_CHANNEL_ID, CUSTOM_SHEET_NAME
    print("=========================================")
    print("      SYSTEM BOT DISCORD & GSHEET        ")
    print("=========================================")
    print("Pilih Fitur yang ingin diaktifkan:")
    print("1. Scan Channel Absen Live")
    print("2. Scan Channel Reward Streamer")
    print("3. Scan Channel Kupon Streamer")
    print("4. Scan Channel Custom (Input Data Sendiri)")
    print("5. Jalankan Fitur 1, 2, dan 3 Secara Berurutan")
    print("=========================================")
    
    while True:
        pilihan = input("Masukkan angka pilihan (1/2/3/4/5): ").strip()
        if pilihan in ["1", "2", "3", "4", "5"]:
            USER_MODE = pilihan
            if pilihan == "4":
                print("\n--- PENGATURAN FITUR 4 ---")
                CUSTOM_CHANNEL_ID = input("Masukkan ID Channel Discord Tujuan: ").strip()
                CUSTOM_SHEET_NAME = input("Masukkan Nama Sheet Tujuan: ").strip()
            break
        else:
            print("Pilihan tidak valid, mohon ketik angka 1, 2, 3, 4, atau 5.")
            
    print("\nMenghubungkan ke Server Discord...")
    client.run(TOKEN)

if __name__ == "__main__":
    main()