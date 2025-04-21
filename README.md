# Computer Network Assignment 1 🌐
A simple implementation of a **BitTorrent-inspired** peer-to-peer file sharing system. Simulate the core behaviors of real-world torrent clients—like seeding, leeching, metadata exchange, and peer discovery—while remaining simple enough to serve as a foundation for learning and experimentation.

---
## 📌 Overview
This project demonstrates the inner workings of the BitTorrent protocol, featuring:
- A **central tracker server** that coordinates peer activity and distributes `.torrent` metadata.
- **Peer clients** that handle uploading (seeding) and downloading (leeching) files in a decentralized swarm.
- A command-line interface (CLI) for managing all core functionalities with ease.
--- 

## ✨ Features
- 📦 Create `.torrent` metadata files from local files/folders  
- 🚀 Seed and distribute files to other peers  
- ⬇️ Leech/download files from the swarm  
- 🔁 Tracker coordination using HTTP endpoints  
- 🔧 CLI commands for all major operations (create, seed, leech, inspect, etc.)  
- ⚙️ Asynchronous peer server for concurrent file handling  
- 🧠 SHA-1 hashing for piece verification  
- 📝 Logging system for tracking peer and system activity
---

## ⚙️ Setup
### 1. 📥 Clone the Repository
```bash
git clone https://github.com/dohuyminhdung/ComputerNetwork_Assignment1
cd ComputerNetwork_Assignment1
```
### 2. 🐍 Create and Activate Virtual Environment
```bash
python -m venv venv
source venv/bin/activate     # On Windows: venv\Scripts\activate
```
### 3. 📦 Install Required Packages
```bash
pip install -r requirements.txt
```

## 🛠️ Configuration
Before running the system, make sure to configure the following (if applicable) 🚀:
- ✅ Update tracker URLs in your CLI commands or default config files  
- ✅ Ensure open ports for peer servers   
- ✅ Check path permissions for reading/writing torrent and data files  
- ✅ Optional: Configure logging level or log output file in config.py or CLI flags  
- 📁 You may also want to set a common directory for shared data between peers during local testing  
```bash
#Go to Peer/peer_config.py
TRACKER_URL = <Your tracker url> 			# For example: "http://127.0.0.1:8000"
PIECE_SIZE: int = <Your default piece length>		# For example: 256 * 1024 (256KB)
DOWNLOAD_DIR = <The dictionary for downloading files>	# For example: "C:\BitTorrent\download"
LOG_DIR = <The ditionary for system diary>		# For example: "D:\BTL1\p2pFileSharingApp" 
```

## 🚀 Usage
### 🤖 For running Tracker Server
```bash
python Tracker.py
```
### 💻 For running Peer Server
```bash
cd Peer		#if you are not at the Peer dictionary
python peer_server.py --port 7000
```
### 🚀 Here are the available commands:
🔍 Connectivity Check
```bash
python peer_cli.py hello --host 127.0.0.1 --port 7000
```
🧬 Create a .torrent File
```bash
python peer_cli.py create --input "/path/to/file"
```
📤 Start Seeding a File
```bash
python peer_cli.py seed --input /path/to/file --port 8001 ...
```
📥 Download (Leech) a File
```bash
python peer_cli.py seed --input /path/to/file --port 6969...
```
🧾 View Torrent Metadata
```bash
python peer_cli.py show-info --torrent /path/to/file.torrent
```
📑 View Status of a Peer
```bash
python peer_cli.py status --port 7891
```
🔧 View commands and their options
```bash
python peer_cli.py --help            #for a full command list
python peer_cli.py <command> --help  #for command options   
```

## 📚 Example Workflow
### 1. Start the Tracker 🌐 
```bash
python Tracker.py
```
### 2. Start the Peer 💻
```bash
cd Peer		#if you are not at the Peer dictionary
python peer_server.py --port 7000
```
### 3. Create and Seed a File 🧬
```bash
python peer_cli.py hello --host 127.0.0.1 --port 7000					#Check the Peer is running or not (Optional)
python peer_cli.py create --input "/path/to/file" --tracker http://localhost:port ...	#Create .torrent file (Optional, seed can automatically create it)
python peer_cli.py seed --input "/path/to/file" --port 7000
python peer_cli.py show-info --torrent created_file.torrent				#view the medata file (Optional)
```
### 4. Leech the File 📥
```bash
python peer_cli.py get-torrent --port 7000
python peer_cli.py leech --torrent downloaded_file.torrent --port 7000
python peer_cli.py status --port 7000		#Check Status of a Peer(Optional)
```

🧪 You can run multiple peers on different ports to simulate swarm activity.  
🚧 For more technical documentation, you can refer to ComputerNetwork_Assignment1.pdf.  
