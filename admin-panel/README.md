# Qdrant Admin Panel

React-based admin panel for managing Qdrant document indexing system.

## Features

- **Dashboard**: Overview of collections, documents, and system status
- **Domain Management**: Create and manage document domains (collections)
- **Document Indexing**: Upload multiple files and index them into selected domains
- **Real-time Progress**: Track indexing progress with visual indicators

## Installation

1. Install dependencies:
```bash
npm install
```

2. Start the development server:
```bash
npm start
```

3. Open [http://localhost:3000](http://localhost:3000) to view it in the browser.

## Usage

### Dashboard
- View system statistics
- Monitor collection status
- Quick access to other sections

### Domain Management
- Create new domains (collections)
- View existing domains with document counts
- Delete domains (with confirmation)

### Document Indexing
1. Select a target domain
2. Upload text files (.txt, .md, .json)
3. Click "Start Indexing" to process files
4. Monitor progress in real-time

## API Integration

The panel integrates with the FastAPI backend running on port 8009:

- `GET /collections` - List all collections
- `POST /collections` - Create new collection
- `DELETE /collections/{name}` - Delete collection
- `GET /collections/{name}/info` - Get collection info
- `POST /index` - Index documents

## Configuration

The app uses a proxy configuration in `package.json` to forward API requests to `http://localhost:8009`.

## Technologies Used

- React 18
- React Router
- Axios for API calls
- React Dropzone for file uploads
- Tailwind CSS for styling
- Lucide React for icons



