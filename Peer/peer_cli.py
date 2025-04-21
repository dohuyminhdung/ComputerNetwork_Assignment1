import asyncio
import click
import os
import logging # Import logging
import requests
from InquirerPy import inquirer
from tabulate import tabulate
from peer import Peer
from peer_torrent import TorrentFile # Để đọc thông tin torrent
from peer_config import LOG_DIR, TRACKER_URL, DOWNLOAD_DIR, PIECE_SIZE  # Import cấu hình

PEER_PORT = 6881
log_file_path = os.path.join(LOG_DIR, 'peer_cli.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', # Thêm tên logger
    handlers=[
        logging.FileHandler(log_file_path),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("PeerCLI") # Tạo logger riêng cho CLI
# --- Kết thúc cấu hình logging ---


@click.group()
def cli():
    """
    PeerTorrent CLI - Simple BitTorrent Client (Direct Interaction Model)
    """
    pass

"""
    Tạo một file .torrent mới từ một file hoặc thư mục.
    Args:
        input_path: Đường dẫn đến file hoặc thư mục nguồn.
        trackers: URL(s) tracker (Hỗ trợ nhiều định dạng)
        output_path: Đường dẫn để lưu file .torrent mới.
        piece_size: Kích thước mỗi mảnh (bytes).
        comment: Note (Optional).
        created_by: Tên ứng dụng hoặc người tạo torrent.
"""
@cli.command()
@click.option('--port', type = int, required=False, default = PEER_PORT, help = "Port for peer server")
@click.option('--input', 'input_path', required=True, type=click.Path(exists=True, readable=True), help = "path to the file(s) you want to seed")
@click.option('--torrent', 'torrent_filepath', required=False, default=None, type=click.Path(exists=True, readable=True), help='Path to the .torrent file to seed.')
@click.option('--tracker', 'tracker_urls', required=False, multiple=True, help='Tracker URL (can specify multiple times).')
@click.option('--piecelen', 'piece_length', type=int, default=262144, show_default=True, help='Piece length in bytes (power of 2).')
@click.option('--cmt', 'comment', type=str, default=None, help='Optional comment for the torrent.')
@click.option('--name', type=str, default=None, help='Name of the torrent file.')
@click.option('--private', is_flag=True, help="Flag to indicate that the torrent should not be publicly discoverable.")
def seed(port, input_path, torrent_filepath, tracker_urls, piece_length, comment, name, private):
    """Uploading file(s)."""
    url = f"http://127.0.0.1:{port}/seed"
    payload = { "input_path": input_path }
    payload["piece_length"] = piece_length
    if tracker_urls: payload["trackers"] = list(tracker_urls)
    if torrent_filepath: payload["torrent_filepath"] = torrent_filepath
    if comment: payload["description"] = comment
    if name: payload["name"] = name
    if private: payload["public"] = False
    reply = requests.post(url, json=payload, timeout=3)
    reply.raise_for_status()
    logging.info(f"{reply.json()['message']}")


@cli.command()
@click.option('--input', 'input_path', required=True, type=click.Path(exists=True, readable=True), help='Path to the file or directory to create torrent.')
@click.option('--tracker', 'tracker_urls', required=False, multiple=True, help='Tracker URL (can specify multiple times).')
@click.option('--output', 'output_path', required=False, type=click.Path(writable=True), help='Path to save the generated .torrent file.')
@click.option('--piecelen', 'piece_length', type=int, default=262144, show_default=True, help='Piece length in bytes (power of 2).')
@click.option('--cmt', 'comment', type=str, default="", help='Optional comment for the torrent.')
@click.option('--cre', 'created_by', type=str, default="", help='Info about the author of the file(s).')
def create(input_path, tracker_urls, output_path, piece_length, comment, created_by):
    """Creates a .torrent file."""
    logger.info(f"Attempting to create torrent file for: {input_path}")
    try:
        success = TorrentFile._create_torrent_file(
            input_path=input_path,
            trackers= tracker_urls or TRACKER_URL,
            output_path= output_path or DOWNLOAD_DIR,
            piece_size= piece_length or PIECE_SIZE,
            comment=comment,
            created_by = created_by
        )
        if success:
           logger.info(f"Torrent file successfully saved to: {output_path}")
           click.echo(f"Torrent file saved to: {output_path}")
        else:
           logger.error(f"Failed to create torrent file for {input_path}.")
           click.echo(f"Failed to create torrent file.", err=True)
    except Exception as e:
        logger.error(f"Error during torrent creation: {e}", exc_info=True)
        click.echo(f"Torrent creation failed: {e}", err=True)

@cli.command()
@click.option('--torrent', 'torrent_filepath', required=True, type=click.Path(exists=True, readable=True), help='Path to the .torrent file to download.')
@click.option('--output-dir', default=DOWNLOAD_DIR, type=click.Path(file_okay=False, writable=True), show_default=True, help='Directory to save downloaded files.')
def download(torrent_filepath, output_dir):
    """Downloads files specified in a .torrent file."""
    logger.info(f"Initializing download for: {torrent_filepath}")
    logger.info(f"Saving to: {output_dir}")
    click.echo(f"Starting download for: {os.path.basename(torrent_filepath)}")
    peer_instance = Peer()
    try:
        # Hàm download trong Peer đã bao gồm tqdm và log
        asyncio.run(peer_instance.download(torrent_filepath=torrent_filepath, output_dir=output_dir))
        # Hàm download nên tự log khi thành công
    except FileNotFoundError as e:
         logger.error(f"Torrent file not found: {e}")
         click.echo(f"Error: Torrent file not found at {torrent_filepath}", err=True)
    except Exception as e:
        logger.error(f"Error during download: {e}", exc_info=True)
        click.echo(f"Download failed: {e}", err=True)


@cli.command(name="show-info") # Đặt tên lệnh khác với biến torrent
@click.option('--torrent', 'torrent_filepath', required=True, type=click.Path(exists=True, readable=True), help='Path to the .torrent file.')
def show_info_cmd(torrent_filepath):
    """Displays detailed information about a .torrent file."""
    logger.info(f"Showing info for: {torrent_filepath}")
    try:
        t_file = TorrentFile(torrent_filepath)
        click.echo(f"--- Torrent Info: {os.path.basename(torrent_filepath)} ---")
        info_data = [
            ("Info Hash", t_file.info_hash_hex),
            ("Announce URL", t_file.tracker_url),
            ("Total Size", f"{t_file.total_size / (1024*1024):.2f} MiB"),
            ("Piece Length", f"{t_file.piece_length / 1024} KiB"),
            ("Number of Pieces", t_file.number_of_pieces),
        ]
        click.echo(tabulate(info_data, tablefmt="plain")) # Dùng "plain" cho cặp key-value


        if t_file.is_multifile:
            click.echo("\nFiles:")
            file_data = [(os.path.join(*f[0]), f"{f[1]/1024:.2f} KiB") for f in t_file.files]
            click.echo(tabulate(file_data, headers=["Path", "Size"], tablefmt="pretty"))
        else:
             click.echo(f"\nFilename: {t_file.filename}")
    except FileNotFoundError as e:
         logger.error(f"Torrent file not found: {e}")
         click.echo(f"Error: Torrent file not found at {torrent_filepath}", err=True)
    except Exception as e:
        logger.error(f"Failed to read torrent info: {e}", exc_info=True)
        click.echo(f"Failed to read torrent info: {e}", err=True)


@cli.command()
@click.option('--port', type=int, default=PEER_PORT, help="Port for peer server")
def get_torrent(port): #fetch
    """Download the .torrent file from peer"""
    url = f"http://127.0.0.1:{port}/torrents"
    request = requests.get(url)
    request.raise_for_status()
    # Parse and print the response
    data: dict = request.json()['data']
    rows = [[key, value["name"], value["description"]] for key, value in data.items()]
    click.echo(tabulate(rows, headers=["info_hash", "Name", "Description"], tablefmt="grid"))

    choices = [(key[:5]+': '+value["name"], key) for key, value in data.items()]
    selected_file = inquirer.select(
        message="Select a torrent file to download:",
        choices= [choice[0] for choice in choices],
        default= choices[0][0],
    ).execute()

    info_hash = next(key for label, key in choices if label == selected_file)
    logging.info(f"Selected file: {info_hash}")
    response = requests.get(url + "/" + info_hash)
    data = response.json()["data"]
    response.raise_for_status()
    logging.info(f"Download torrent file {info_hash} successfully.\nFilepath: {data}")

@cli.command()
@click.option('--port', type = int, required=False, default = PEER_PORT, help = "Port for peer server")
@click.option('--torrent', 'torrent_filepath', required=True, type=click.Path(exists=True, readable=True), help='Path to the .torrent file need to leech.')
def leech(port, torrent_filepath):
    """Downloading file(s) from the .torrent file"""
    url = f"http://127.0.0.1:{port}/leech"
    payload = {"torrent_filepath": torrent_filepath}
    reply = requests.post(url, json=payload, timeout=10)
    reply.raise_for_status()
    data = reply.json()
    click.echo(f"{data['message']} ...")

@cli.command()
@click.option('--port', type=int, default=PEER_PORT, help="Port for peer server.")
def status(port):
    """View the status of a peer"""
    url = f"http://127.0.0.1:{port}/status"
    request = requests.get(url)
    request.raise_for_status()
    data = request.json()

    seeding_data: list = data['seeding']
    click.echo("SEEDING FILES:")
    click.echo(tabulate(
        seeding_data,
        headers=["info_hash", "filepath"],
        tablefmt="grid")
    )

    leeching_data: list = data["leeching"]
    click.echo("LEECHING FILES:")
    click.echo(tabulate(
        leeching_data,
        headers=["info_hash", "filepath", "status"],
        tablefmt="grid"
    ))


@cli.command()
@click.option('--port', type=int, required=True, help='Port to check connectivity.')
@click.option('--host', type=str, default="127.0.0.1", help='Host address to check connectivity (default: 127.0.0.1).')
def hello(host, port):
    """
    Check connectivity to a specified host and port.
    Example:
      python check_connection.py --port 7000
      python check_connection.py --host 192.168.1.100 --port 7000
    """
    url = f"http://{host}:{port}/"
    try:
        response = requests.get(url, timeout=10, verify=False)
        response.raise_for_status()
        click.echo(f"Successfully connected to {url}. Status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        click.echo(f"Failed to connect to {url}. Error: {e}")

#"G:\Y3S2\MMT\Slide\Chapter_8_v8.0.pdf"
#"G:\Y3S2\MMT\Slide\Chapter_7_v8.0.pdf"
if __name__ == '__main__':
    # Đảm bảo các thư mục cần thiết tồn tại
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    cli()