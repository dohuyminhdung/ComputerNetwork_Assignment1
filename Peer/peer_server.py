import asyncio
import click
import uvicorn
from quart import Quart, request, jsonify, abort # Import các thành phần Quart
from random import randint
from peer import Peer
from peer_config import *


DEFAULT_PORT = 6881
pbar_pos = 0

# --- Khởi tạo đối tượng Peer toàn cục ---
API_PORT = int(os.getenv("PEER_API_PORT", 8000))
PEER_PORT = randint(4000, 8000)
PEER_IP = os.getenv("PEER_IP", '0.0.0.0')

try:
     peer_instance = Peer(peer_port=PEER_PORT)
     # logger.info(f"Peer instance created, will listen for P2P on {PEER_IP}:{PEER_PORT}")
except TypeError:
     logger.warning(f"Peer.__init__ does not accept ip_address/port arguments? Using defaults.")
     peer_instance = Peer()

# --- Khởi tạo ứng dụng Quart ---
app = Quart(__name__)
@app.route("/")
# --- Hàm trợ giúp để chạy hàm blocking (Giữ nguyên) ---
async def root():
    return {"message": "Hello, world!"}
# --- Định nghĩa các Endpoint API với Quart ---

@app.route("/", methods=["GET"])
async def get_root():
    """Kiểm tra trạng thái hoạt động của API server."""
    # Quart >= 0.19 tự động jsonify dicts
    # return jsonify({"status": "OK"})
    return {"status": "OK"} # Trả về dict trực tiếp


@app.route("/status")
def get_status():
    stat= {}
    """
    self.seeding_torrents[torrent.info_hash] = {
                "torrent_filepath": torrent.filepath,
                "filepath": input_path
            }
    """
    stat["seeding"] = [[
        info_hash.hex(),
        iterator["filepath"]
        ] for info_hash, iterator in peer_instance.seeding_torrents.items() ]

    stat["leeching"] = [[
        info_hash.hex(), 
        piece_manager.output_name, 
        piece_manager.percent_of_downloaded
        ] for info_hash, piece_manager in peer_instance.leeching_torrents.items()]
    return jsonify(stat), 200
 
# @app.route("/status", methods=["GET"])
# async def get_overall_status():
#     """Lấy trạng thái tổng thể của các torrent đang quản lý."""
#     seeding_list_data = []
#     downloading_list_data = []

#     # Lấy trạng thái seeding
#     for info_hash, data in peer_instance.seeding_torrents.items():
#         torrent_obj = data.get("torrent_object")
#         status_data = {
#             "info_hash": info_hash,
#             "filepath": data.get("filepath"),
#             "total_size": data.get("total_size"),
#             "is_multifile": data.get("is_multifile"),
#         }
#         seeding_list_data.append(status_data)

#     # Lấy trạng thái downloading chua lam cai nay
#     for info_hash, data in peer_instance.leeching_torrents.items():
#         torrent_obj = data.get("torrent_object")

#     # Validate response tổng thể (tùy chọn)
#     response_data = {"seeding": seeding_list_data, "downloading": downloading_list_data}
#     return jsonify(response_data)


@app.route("/seed", methods=["POST"])
async def start_seed_torrent():
    """Bắt đầu seeding một torrent mới hoặc từ file .torrent có sẵn."""
    try:
        # Lấy JSON từ request
        json_data = await request.get_json()
        if not json_data:
            abort(400, description="Request body must be JSON.")

        input_path = json_data.get("input_path", "")
        if input_path == "":
            return jsonify({"error": "input path not found"}), 400
        piece_length = json_data.get("piece_length", None)
        # logger.info(
        #     f"Calling _sow_seed with: input_path='{input_path}' (type: {type(input_path)}), piece_length={piece_length} (type: {type(piece_length)})")
        peer_instance._sow_seed(
            input_path=input_path,
            trackers=json_data.get("trackers",TRACKER_URL),
            public=True,
            piece_length=piece_length,
            torrent_filepath=json_data.get("torrent_filepath", None),
            name=json_data.get("name", None),
            description=json_data.get("description", None)
        )
        return jsonify({"message": f"Start seeding {input_path}"}), 200

    except Exception as e:
        logger.error(f"Error parsing seed request: {e}")
        #  abort(400, description="Could not parse request body.")
        return jsonify({"error": "cannot start seeding: " + str(e)}), 500



@app.route("/torrents", methods=["GET"])
async def get_torrents():
    try:
        torrents = Peer.get_torrents()
        return jsonify({"data": torrents}), 200
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/leech", methods=["POST"])
async def start_leech_torrent():
    """Bắt đầu tải về (leeching) một torrent."""
    try:
        json_data = await request.get_json()
        if not json_data:
            return jsonify({"error": "Request body must be JSON."}), 400
        torrent_filepath = json_data.get("torrent_filepath")
        if not torrent_filepath:
            return jsonify({"error": f"Torrent file {torrent_filepath} not found."}), 400
        if not os.path.exists(torrent_filepath):
            return jsonify({"error": f"File {torrent_filepath} not found."}), 400

        global pbar_pos
        logger.debug(f"Current pbar_pos: {pbar_pos}")
        pbar_pos += 1
        # asyncio.create_task(peer_instance._download(torrent_filepath, pbar_pos%10))
        asyncio.create_task(peer_instance._download(torrent_filepath=torrent_filepath,
                                                    pbar_position=pbar_pos%10))
        logger.debug(f"New pbar_pos: {pbar_pos}")
        return jsonify(
            {"message": "Download process initiated in background.", "torrent_file": torrent_filepath}), 200

    except Exception as e:
        logger.error(f"Failed to initiate download task: {e}", exc_info=True)
        return jsonify({"error":"Failed to initiate download task" + str(e)}), 500
    


# Sử dụng type hint <string:info_hash> để Quart tự parse path param
@app.route("/torrents/<string:info_hash>", methods=["GET"])
async def get_torrent_by_info_hash(info_hash):
    try:
        filepath = await Peer._get_torrent_by_info_hash(info_hash)
        return jsonify({"data": filepath}), 200
    except Exception as e:
        logger.error(f"Failed to get torrent by info hash in server: {e}", exc_info=True)
        return jsonify({"error":"Failed to to get torrent by info hash" + str(e)}), 500


@app.before_serving
async def run_background_tasks():
    asyncio.create_task(peer_instance.start_seeding())
# --- Chạy Server (sử dụng hypercorn hoặc uvicorn từ terminal) ---
@click.command()
@click.option("--port", "port", default=6881, help="Running port for peer server")
def main(port):
    print(f"Running peer server on port {port}")
    uvicorn.run(f"peer_server:app",
                host="127.0.0.1",
                port=port,
                reload=False)
#"G:\Y3S2\MMT\Slide\Chapter_8_v8.0.pdf"
if __name__ == '__main__':
    # Đảm bảo các thư mục cần thiết tồn tại
    main()