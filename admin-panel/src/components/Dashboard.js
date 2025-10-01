import React, { useState, useEffect } from 'react';
import { Database, FileText, Search, Activity } from 'lucide-react';
import axios from 'axios';

const Dashboard = () => {
  const [stats, setStats] = useState({
    totalCollections: 0,
    totalDocuments: 0,
    indexedVectors: 0,
    systemStatus: 'unknown'
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    try {
      setLoading(true);
      
      // Получаем список коллекций
      const collectionsResponse = await axios.get('/collections');
      console.log('Dashboard: Collections response:', collectionsResponse.data);
      
      // Проверяем структуру ответа
      let collections;
      if (Array.isArray(collectionsResponse.data)) {
        // Если ответ - массив (старый формат)
        collections = collectionsResponse.data;
      } else if (collectionsResponse.data.collections) {
        // Если ответ - объект с полем collections (новый формат)
        collections = collectionsResponse.data.collections;
      } else {
        collections = [];
      }
      
      let totalDocuments = 0;
      let totalIndexedVectors = 0;
      
      // Получаем детальную информацию по каждой коллекции
      for (const collection of collections) {
        try {
          const infoResponse = await axios.get(`/collections/${collection.name}/info`);
          const info = infoResponse.data;
          totalDocuments += info.points_count || 0;
          totalIndexedVectors += info.indexed_vectors_count || 0;
        } catch (error) {
          console.error(`Error fetching info for collection ${collection.name}:`, error);
        }
      }
      
      setStats({
        totalCollections: collections.length,
        totalDocuments,
        indexedVectors: totalIndexedVectors,
        systemStatus: 'online'
      });
    } catch (error) {
      console.error('Error fetching stats:', error);
      setStats(prev => ({ ...prev, systemStatus: 'offline' }));
    } finally {
      setLoading(false);
    }
  };

  const statCards = [
    {
      name: 'Collections',
      value: stats.totalCollections,
      icon: Database,
      color: 'text-blue-600',
      bgColor: 'bg-blue-100'
    },
    {
      name: 'Documents',
      value: stats.totalDocuments,
      icon: FileText,
      color: 'text-green-600',
      bgColor: 'bg-green-100'
    },
    {
      name: 'Indexed Vectors',
      value: stats.indexedVectors,
      icon: Search,
      color: 'text-purple-600',
      bgColor: 'bg-purple-100'
    },
    {
      name: 'System Status',
      value: stats.systemStatus === 'online' ? 'Online' : 'Offline',
      icon: Activity,
      color: stats.systemStatus === 'online' ? 'text-green-600' : 'text-red-600',
      bgColor: stats.systemStatus === 'online' ? 'bg-green-100' : 'bg-red-100'
    }
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="mt-1 text-sm text-gray-500">
          Overview of your Qdrant document indexing system
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {statCards.map((card) => {
          const Icon = card.icon;
          return (
            <div key={card.name} className="bg-white overflow-hidden shadow rounded-lg">
              <div className="p-5">
                <div className="flex items-center">
                  <div className="flex-shrink-0">
                    <div className={`p-3 rounded-md ${card.bgColor}`}>
                      <Icon className={`h-6 w-6 ${card.color}`} />
                    </div>
                  </div>
                  <div className="ml-5 w-0 flex-1">
                    <dl>
                      <dt className="text-sm font-medium text-gray-500 truncate">
                        {card.name}
                      </dt>
                      <dd className="text-lg font-medium text-gray-900">
                        {loading ? '...' : card.value}
                      </dd>
                    </dl>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Quick Actions */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-4 py-5 sm:p-6">
          <h3 className="text-lg leading-6 font-medium text-gray-900">
            Quick Actions
          </h3>
          <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <button
              onClick={fetchStats}
              className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
            >
              <Activity className="mr-2 h-4 w-4" />
              Refresh Stats
            </button>
            <a
              href="/domains"
              className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
            >
              <Database className="mr-2 h-4 w-4" />
              Manage Domains
            </a>
            <a
              href="/indexing"
              className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
            >
              <FileText className="mr-2 h-4 w-4" />
              Start Indexing
            </a>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
