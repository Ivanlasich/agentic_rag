import React, { useState, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, FileText, Database, Play, CheckCircle, AlertCircle, X } from 'lucide-react';
import axios from 'axios';

const IndexingPanel = () => {
  const [collections, setCollections] = useState([]);
  const [selectedDomain, setSelectedDomain] = useState('');
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [indexing, setIndexing] = useState(false);
  const [indexingProgress, setIndexingProgress] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCollections();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchCollections = async () => {
    try {
      setLoading(true);
      console.log('Fetching collections...');
      const response = await axios.get('/collections');
      console.log('Collections response:', response.data);
      
      // Проверяем структуру ответа
      let collectionsData;
      if (Array.isArray(response.data)) {
        // Если ответ - массив (новый формат)
        collectionsData = response.data;
      } else if (response.data.collections) {
        // Если ответ - объект с полем collections (старый формат)
        collectionsData = response.data.collections;
      } else {
        collectionsData = [];
      }
      
      console.log('Collections data:', collectionsData);
      setCollections(collectionsData);
      
      // Автоматически выбираем первую коллекцию
      if (collectionsData.length > 0 && !selectedDomain) {
        setSelectedDomain(collectionsData[0].name);
        console.log('Selected domain:', collectionsData[0].name);
      }
    } catch (error) {
      console.error('Error fetching collections:', error);
      console.error('Error details:', error.response?.data);
    } finally {
      setLoading(false);
    }
  };


  const onDrop = (acceptedFiles) => {
    const newFiles = acceptedFiles.map(file => ({
      file,
      id: Math.random().toString(36).substr(2, 9),
      name: file.name,
      size: file.size,
      type: file.type,
      status: 'ready'
    }));
    
    setUploadedFiles(prev => [...prev, ...newFiles]);
  };

  const removeFile = (fileId) => {
    setUploadedFiles(prev => prev.filter(f => f.id !== fileId));
  };

  const startIndexing = async () => {
    if (!selectedDomain || uploadedFiles.length === 0) {
      alert('Please select a domain and upload at least one file');
      return;
    }

    try {
      setIndexing(true);
      setIndexingProgress({ current: 0, total: uploadedFiles.length, status: 'Starting...' });

      const formData = new FormData();
      
      // Добавляем файлы
      uploadedFiles.forEach(fileObj => {
        formData.append('files', fileObj.file);
      });

      // Добавляем домен
      formData.append('domain', selectedDomain);

      // Отправляем запрос на индексацию
      const response = await axios.post('/index', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        onUploadProgress: (progressEvent) => {
          const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          setIndexingProgress({
            current: Math.floor((percentCompleted / 100) * uploadedFiles.length),
            total: uploadedFiles.length,
            status: `Uploading... ${percentCompleted}%`
          });
        },
        timeout: 300000 // 5 minutes timeout
      });

      // Обновляем статус файлов
      setUploadedFiles(prev => 
        prev.map(f => ({ ...f, status: 'indexed' }))
      );

      setIndexingProgress({
        current: uploadedFiles.length,
        total: uploadedFiles.length,
        status: 'Completed!'
      });

      // Показываем результат
      alert(`Successfully indexed ${response.data.documents_indexed} documents into collection "${response.data.collection_name}"`);

    } catch (error) {
      console.error('Error during indexing:', error);
      
      // Обновляем статус файлов на ошибку
      setUploadedFiles(prev => 
        prev.map(f => ({ ...f, status: 'error' }))
      );

      setIndexingProgress({
        current: 0,
        total: uploadedFiles.length,
        status: 'Error occurred'
      });

      alert('Error during indexing: ' + (error.response?.data?.detail || error.message));
    } finally {
      setIndexing(false);
      // Сбрасываем прогресс через 3 секунды
      setTimeout(() => {
        setIndexingProgress(null);
      }, 3000);
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const getFileStatusIcon = (status) => {
    switch (status) {
      case 'ready': return <FileText className="h-4 w-4 text-gray-400" />;
      case 'indexed': return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'error': return <AlertCircle className="h-4 w-4 text-red-500" />;
      default: return <FileText className="h-4 w-4 text-gray-400" />;
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/plain': ['.txt'],
      'text/markdown': ['.md'],
      'application/json': ['.json'],
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/vnd.ms-excel': ['.xls'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'text/csv': ['.csv']
    },
    multiple: true
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Document Indexing</h1>
        <p className="mt-1 text-sm text-gray-500">
          Upload and index documents into Qdrant collections
        </p>
      </div>

      {/* Domain Selection */}
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Select Domain</h3>
        {loading ? (
          <div className="text-center py-4">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary-600 mx-auto"></div>
            <p className="mt-2 text-sm text-gray-500">Loading domains...</p>
          </div>
        ) : (
          <div>
            <div className="mb-4 text-sm text-gray-600">
              Collections loaded: {collections.length}, Selected: {selectedDomain || 'none'}
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {collections.map((collection) => (
                <button
                  key={collection.name}
                  onClick={() => {
                    console.log('Selecting domain:', collection.name);
                    setSelectedDomain(collection.name);
                  }}
                  className={`p-4 border-2 rounded-lg text-left transition-colors ${
                    selectedDomain === collection.name
                      ? 'border-primary-500 bg-primary-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="flex items-center">
                    <Database className="h-5 w-5 text-gray-400 mr-3" />
                    <div>
                      <div className="text-sm font-medium text-gray-900">
                        {collection.name}
                      </div>
                      <div className="text-xs text-gray-500">
                        Click to select
                      </div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
            {collections.length === 0 && (
              <div className="text-center py-8 text-gray-500">
                No domains available. Create a domain first.
              </div>
            )}
          </div>
        )}
      </div>


      {/* File Upload */}
      <div className="bg-white shadow rounded-lg p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Upload Files</h3>
        
        <div
          {...getRootProps()}
          className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
            isDragActive
              ? 'border-primary-500 bg-primary-50'
              : 'border-gray-300 hover:border-gray-400'
          }`}
        >
          <input {...getInputProps()} />
          <Upload className="mx-auto h-12 w-12 text-gray-400" />
          <p className="mt-2 text-sm text-gray-600">
            {isDragActive
              ? 'Drop the files here...'
              : 'Drag & drop files here, or click to select files'}
          </p>
          <p className="text-xs text-gray-500 mt-1">
            Supports: .txt, .md, .json, .pdf, .docx, .xlsx, .xls, .csv files
          </p>
        </div>

        {/* Uploaded Files List */}
        {uploadedFiles.length > 0 && (
          <div className="mt-6">
            <h4 className="text-sm font-medium text-gray-900 mb-3">Uploaded Files</h4>
            <div className="space-y-2">
              {uploadedFiles.map((fileObj) => (
                <div
                  key={fileObj.id}
                  className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
                >
                  <div className="flex items-center">
                    {getFileStatusIcon(fileObj.status)}
                    <div className="ml-3">
                      <div className="text-sm font-medium text-gray-900">
                        {fileObj.name}
                      </div>
                      <div className="text-xs text-gray-500">
                        {formatFileSize(fileObj.size)}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => removeFile(fileObj.id)}
                    className="text-gray-400 hover:text-gray-600"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Indexing Progress */}
      {indexingProgress && (
        <div className="bg-white shadow rounded-lg p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Indexing Progress</h3>
          <div className="space-y-3">
            <div className="flex justify-between text-sm">
              <span>{indexingProgress.status}</span>
              <span>{indexingProgress.current} / {indexingProgress.total}</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className="bg-primary-600 h-2 rounded-full transition-all duration-300"
                style={{
                  width: `${(indexingProgress.current / indexingProgress.total) * 100}%`
                }}
              ></div>
            </div>
          </div>
        </div>
      )}

      {/* Start Indexing Button */}
      <div className="bg-white shadow rounded-lg p-6">
        <div className="flex justify-between items-center">
          <div>
            <h3 className="text-lg font-medium text-gray-900">Ready to Index</h3>
            <p className="text-sm text-gray-500">
              {uploadedFiles.length} files ready for indexing into "{selectedDomain}"
            </p>
          </div>
          <button
            onClick={startIndexing}
            disabled={!selectedDomain || uploadedFiles.length === 0 || indexing}
            className="inline-flex items-center px-6 py-3 border border-transparent text-base font-medium rounded-md shadow-sm text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Play className="mr-2 h-5 w-5" />
            {indexing ? 'Indexing...' : 'Start Indexing'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default IndexingPanel;
