import React, { useState, useEffect } from 'react';
import { Plus, Trash2, Database, FileText, Search, ChevronDown, ChevronRight, Folder, RefreshCw, X } from 'lucide-react';
import axios from 'axios';

const DomainManager = () => {
  const [collections, setCollections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newDomainName, setNewDomainName] = useState('');
  const [creating, setCreating] = useState(false);
  const [expandedDomain, setExpandedDomain] = useState(null);
  const [domainFiles, setDomainFiles] = useState({});
  const [loadingFiles, setLoadingFiles] = useState(false);

  useEffect(() => {
    fetchCollections();
  }, []);

  const fetchCollections = async () => {
    try {
      setLoading(true);
      console.log('DomainManager: Fetching collections...');
      const response = await axios.get('/collections');
      console.log('DomainManager: Collections response:', response.data);
      
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
      
      console.log('DomainManager: Collections data:', collectionsData);
      
      // Получаем детальную информацию для каждой коллекции
      const collectionsWithInfo = await Promise.all(
        collectionsData.map(async (collection) => {
          try {
            const infoResponse = await axios.get(`/collections/${collection.name}/info`);
            return {
              name: collection.name,
              ...infoResponse.data
            };
          } catch (error) {
            console.error(`Error fetching info for ${collection.name}:`, error);
            return {
              name: collection.name,
              points_count: 0,
              indexed_vectors_count: 0,
              status: 'unknown'
            };
          }
        })
      );
      
      setCollections(collectionsWithInfo);
      
      // Автоматически загружаем файлы для всех коллекций
      await loadFilesForAllCollections(collectionsWithInfo);
    } catch (error) {
      console.error('Error fetching collections:', error);
      console.error('Error details:', error.response?.data);
    } finally {
      setLoading(false);
    }
  };

  const loadFilesForAllCollections = async (collections) => {
    if (collections.length === 0) return;
    
    setLoadingFiles(true);
    try {
      // Загружаем файлы для всех коллекций параллельно
      const filePromises = collections.map(async (collection) => {
        try {
          const response = await axios.get(`/collections/${collection.name}/files`);
          return {
            domainName: collection.name,
            files: response.data.files || []
          };
        } catch (error) {
          console.error(`Error fetching files for ${collection.name}:`, error);
          return {
            domainName: collection.name,
            files: []
          };
        }
      });

      const results = await Promise.all(filePromises);
      
      // Обновляем состояние с файлами для всех доменов
      const newDomainFiles = {};
      results.forEach(result => {
        newDomainFiles[result.domainName] = result.files;
      });
      
      setDomainFiles(newDomainFiles);
    } finally {
      setLoadingFiles(false);
    }
  };

  const fetchDomainFiles = async (domainName) => {
    try {
      const response = await axios.get(`/collections/${domainName}/files`);
      setDomainFiles(prev => ({
        ...prev,
        [domainName]: response.data.files || []
      }));
    } catch (error) {
      console.error(`Error fetching files for ${domainName}:`, error);
      setDomainFiles(prev => ({
        ...prev,
        [domainName]: []
      }));
    }
  };

  const toggleDomainExpansion = (domainName) => {
    if (expandedDomain === domainName) {
      setExpandedDomain(null);
    } else {
      setExpandedDomain(domainName);
      // Файлы уже загружены автоматически при загрузке страницы
      // Но если по какой-то причине их нет, загружаем
      if (!domainFiles[domainName]) {
        fetchDomainFiles(domainName);
      }
    }
  };

  const createDomain = async (e) => {
    e.preventDefault();
    if (!newDomainName.trim()) return;

    try {
      setCreating(true);
      // Создаем пустую коллекцию
      await axios.post('/collections', {
        collection_name: newDomainName.toLowerCase().replace(/\s+/g, '_'),
        vectors_config: {
          size: 1024,
          distance: 'Cosine'
        }
      });
      
      const createdDomainName = newDomainName.toLowerCase().replace(/\s+/g, '_');
      setNewDomainName('');
      setShowCreateForm(false);
      await fetchCollections();
      
      // Автоматически загружаем файлы для нового домена
      await fetchDomainFiles(createdDomainName);
    } catch (error) {
      console.error('Error creating domain:', error);
      alert('Error creating domain: ' + (error.response?.data?.detail || error.message));
    } finally {
      setCreating(false);
    }
  };

  const deleteFile = async (collectionName, filename) => {
    if (!window.confirm(`Are you sure you want to delete file "${filename}" from domain "${collectionName}"? This will trigger reindexing.`)) {
      return;
    }

    try {
      const response = await axios.delete(`/collections/${collectionName}/files/${filename}`);
      alert(response.data.message);
      
      // Обновляем список файлов
      await fetchDomainFiles(collectionName);
      // Обновляем информацию о коллекции
      await fetchCollections();
    } catch (error) {
      console.error('Error deleting file:', error);
      alert('Error deleting file: ' + (error.response?.data?.detail || error.message));
    }
  };

  const reindexDomain = async (collectionName) => {
    if (!window.confirm(`Are you sure you want to reindex domain "${collectionName}"? This will clear and rebuild the entire index.`)) {
      return;
    }

    try {
      const response = await axios.post(`/collections/${collectionName}/reindex`);
      alert(response.data.message);
      
      // Обновляем информацию о коллекции
      await fetchCollections();
    } catch (error) {
      console.error('Error reindexing domain:', error);
      alert('Error reindexing domain: ' + (error.response?.data?.detail || error.message));
    }
  };

  const deleteCollection = async (collectionName) => {
    if (!window.confirm(`Are you sure you want to delete collection "${collectionName}"? This action cannot be undone.`)) {
      return;
    }

    try {
      await axios.delete(`/collections/${collectionName}`);
      await fetchCollections();
    } catch (error) {
      console.error('Error deleting collection:', error);
      alert('Error deleting collection: ' + (error.response?.data?.detail || error.message));
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'green': return 'text-green-600 bg-green-100';
      case 'yellow': return 'text-yellow-600 bg-yellow-100';
      case 'red': return 'text-red-600 bg-red-100';
      default: return 'text-gray-600 bg-gray-100';
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Domain Management</h1>
          <p className="mt-1 text-sm text-gray-500">
            Create and manage document domains (collections)
          </p>
        </div>
        <button
          onClick={() => setShowCreateForm(true)}
          className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
        >
          <Plus className="mr-2 h-4 w-4" />
          Create Domain
        </button>
      </div>

      {/* Create Domain Form */}
      {showCreateForm && (
        <div className="bg-white shadow rounded-lg p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Create New Domain</h3>
          <form onSubmit={createDomain} className="space-y-4">
            <div>
              <label htmlFor="domainName" className="block text-sm font-medium text-gray-700">
                Domain Name
              </label>
              <input
                type="text"
                id="domainName"
                value={newDomainName}
                onChange={(e) => setNewDomainName(e.target.value)}
                className="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
                placeholder="e.g., literature, technical, legal"
                required
              />
              <p className="mt-1 text-xs text-gray-500">
                Domain name will be converted to lowercase and spaces replaced with underscores
              </p>
            </div>
            <div className="flex justify-end space-x-3">
              <button
                type="button"
                onClick={() => setShowCreateForm(false)}
                className="px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={creating}
                className="px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50"
              >
                {creating ? 'Creating...' : 'Create Domain'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Collections List */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-4 py-5 sm:p-6">
          <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">
            Existing Domains
          </h3>
          
          {loading ? (
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600 mx-auto"></div>
              <p className="mt-2 text-sm text-gray-500">Loading collections...</p>
            </div>
          ) : collections.length === 0 ? (
            <div className="text-center py-8">
              <Database className="mx-auto h-12 w-12 text-gray-400" />
              <h3 className="mt-2 text-sm font-medium text-gray-900">No domains</h3>
              <p className="mt-1 text-sm text-gray-500">Get started by creating a new domain.</p>
              <div className="mt-4 text-xs text-gray-400">
                Debug: Collections loaded: {collections.length}
              </div>
            </div>
          ) : (
            <div>
              <div className="mb-4 text-sm text-gray-600">
                Debug: Collections loaded: {collections.length}, Files loading: {loadingFiles ? 'Yes' : 'No'}
              </div>
            <div className="overflow-hidden">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Domain Name
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Documents
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Indexed Vectors
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Files
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {collections.map((collection) => (
                    <React.Fragment key={collection.name}>
                      <tr>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="flex items-center">
                            <Database className="h-5 w-5 text-gray-400 mr-3" />
                            <div className="text-sm font-medium text-gray-900">
                              {collection.name}
                            </div>
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="flex items-center">
                            <FileText className="h-4 w-4 text-gray-400 mr-2" />
                            <span className="text-sm text-gray-900">
                              {collection.points_count || 0}
                            </span>
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="flex items-center">
                            <Search className="h-4 w-4 text-gray-400 mr-2" />
                            <span className="text-sm text-gray-900">
                              {collection.indexed_vectors_count || 0}
                            </span>
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getStatusColor(collection.status)}`}>
                            {collection.status || 'unknown'}
                          </span>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <button
                            onClick={() => toggleDomainExpansion(collection.name)}
                            className="flex items-center text-sm text-gray-600 hover:text-gray-900"
                          >
                            {expandedDomain === collection.name ? (
                              <ChevronDown className="h-4 w-4 mr-1" />
                            ) : (
                              <ChevronRight className="h-4 w-4 mr-1" />
                            )}
                          <Folder className="h-4 w-4 mr-1" />
                          {loadingFiles ? '...' : (domainFiles[collection.name]?.length || 0)} files
                          </button>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                          <button
                            onClick={() => deleteCollection(collection.name)}
                            className="text-red-600 hover:text-red-900"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </td>
                      </tr>
                      {expandedDomain === collection.name && (
                        <tr>
                        <td colSpan="6" className="px-6 py-4 bg-gray-50">
                          <div className="space-y-3">
                            <div className="flex items-center justify-between">
                              <h4 className="text-sm font-medium text-gray-900">Files in {collection.name}</h4>
                              {domainFiles[collection.name]?.length > 0 && (
                                <button
                                  onClick={() => reindexDomain(collection.name)}
                                  className="inline-flex items-center px-2 py-1 text-xs font-medium text-white bg-blue-600 rounded hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                                >
                                  <RefreshCw className="h-3 w-3 mr-1" />
                                  Reindex
                                </button>
                              )}
                            </div>
                            {domainFiles[collection.name]?.length > 0 ? (
                              <div className="grid grid-cols-1 gap-2">
                                {domainFiles[collection.name].map((file, index) => (
                                  <div key={index} className="flex items-center justify-between p-2 bg-white rounded border">
                                    <div className="flex items-center">
                                      <FileText className="h-4 w-4 text-gray-400 mr-2" />
                                      <span className="text-sm text-gray-900">{file.name}</span>
                                      <span className="text-xs text-gray-500 ml-2">
                                        ({Math.round(file.size / 1024)} KB)
                                      </span>
                                    </div>
                                    <div className="flex items-center space-x-2">
                                      <span className="text-xs text-gray-500">
                                        {new Date(file.modified * 1000).toLocaleDateString()}
                                      </span>
                                      <button
                                        onClick={() => deleteFile(collection.name, file.name)}
                                        className="text-red-600 hover:text-red-800 focus:outline-none"
                                        title="Delete file"
                                      >
                                        <X className="h-4 w-4" />
                                      </button>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <p className="text-sm text-gray-500">No files uploaded yet</p>
                            )}
                          </div>
                        </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default DomainManager;
