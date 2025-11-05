import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Car, TrendingUp, Clock, Activity, AlertCircle, Loader, Navigation } from 'lucide-react';

const StatCard = ({ icon: Icon, title, value, subtitle, color, isLoading }) => (
  <div className="bg-white rounded-lg shadow-lg p-6 border-l-4" style={{ borderLeftColor: color }}>
    <div className="flex items-center justify-between">
      <div>
        <p className="text-sm font-medium text-gray-600">{title}</p>
        {isLoading ? (
          <div className="flex items-center mt-2">
            <Loader className="h-6 w-6 text-gray-400 animate-spin mr-2" />
            <span className="text-gray-400">Carregando...</span>
          </div>
        ) : (
          <>
            <p className="text-3xl font-bold text-gray-900">{value}</p>
            {subtitle && <p className="text-sm text-gray-500 mt-1">{subtitle}</p>}
          </>
        )}
      </div>
      <Icon className="h-12 w-12 text-gray-400" style={{ color }} />
    </div>
  </div>
);

const ErrorMessage = ({ message, onRetry }) => (
  <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
    <div className="flex items-center">
      <AlertCircle className="h-5 w-5 text-red-400 mr-2" />
      <div className="flex-1">
        <h3 className="text-sm font-medium text-red-800">Erro ao carregar dados</h3>
        <p className="text-sm text-red-600 mt-1">{message}</p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="bg-red-100 hover:bg-red-200 text-red-800 px-3 py-1 rounded text-sm font-medium transition-colors"
        >
          Tentar novamente
        </button>
      )}
    </div>
  </div>
);

const TrafficDashboard = () => {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentTime, setCurrentTime] = useState(new Date());
  const [lastUpdate, setLastUpdate] = useState(null);
  const [connectionStatus, setConnectionStatus] = useState('connecting');
  const [selectedLane, setSelectedLane] = useState('lane_1');
  const [availableLanes] = useState(['lane_1', 'lane_2', 'lane_3']);
  const [dataAge, setDataAge] = useState(null);

  const testConnection = async () => {
    try {
      const response = await fetch('http://192.168.0.3:8080/health');
      if (response.ok) {
        const healthData = await response.json();
        console.log('API Health:', healthData);
        setConnectionStatus('connected');
        return true;
      } else {
        setConnectionStatus('error');
        return false;
      }
    } catch (err) {
      console.error('Connection test failed:', err);
      setConnectionStatus('error');
      return false;
    }
  };

  const fetchData = async (laneId = selectedLane) => {
    try {
      setError(null);
      
      const isConnected = await testConnection();
      if (!isConnected) {
        throw new Error('Não foi possível conectar com a API. Verifique se o servidor está rodando.');
      }

      const endpoint = laneId ? `http://192.168.0.3:8080/data/${laneId}` : 'http://192.168.0.3:8080/data';
      console.log('Fetching from:', endpoint);
      
      const response = await fetch(endpoint);
      
      if (!response.ok) {
        throw new Error(`Erro HTTP: ${response.status} - ${response.statusText}`);
      }
      
      const contentType = response.headers.get("content-type");
      if (!contentType || !contentType.includes("application/json")) {
        throw new Error('Resposta da API não é um JSON válido');
      }

      const rawData = await response.json();
      
      console.log('Dados recebidos da API:', rawData);

      if (!Array.isArray(rawData)) {
        throw new Error('Formato de dados inválido recebido da API');
      }

      if (rawData.length === 0) {
        setData([]);
        setLastUpdate(new Date());
        setLoading(false);
        setConnectionStatus('connected');
        return;
      }

      const transformedData = rawData.map((item, index) => {
        let timestamp;
        
        if (item.timestamp && item.timestamp > 0) {
          timestamp = item.timestamp > 10000000000 ? item.timestamp : item.timestamp * 1000;
        } else {
          timestamp = Date.now() - (rawData.length - index) * 300000;
        }

        const date = new Date(timestamp);
        
        return {
          timestamp: Math.floor(timestamp / 1000),
          current_cars: Math.round(item.current_cars || 0),
          datetime: item.datetime || date.toISOString(),
          rolling_average: Number((item.rolling_average || 0).toFixed(1)),
          total_count: Math.round(item.total_count || 0),
          lane_id: item.lane_id || laneId || 'lane_1',
          hour: date.toLocaleTimeString('pt-BR', { 
            hour: '2-digit', 
            minute: '2-digit' 
          }),
          fullDate: date.toLocaleDateString('pt-BR', {
            day: '2-digit',
            month: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
          })
        };
      });

      transformedData.sort((a, b) => a.timestamp - b.timestamp);
      
      const uniqueData = transformedData.filter((item, index, arr) => 
        index === 0 || arr[index - 1].timestamp !== item.timestamp
      );
      
      console.log('Dados transformados:', uniqueData);
      
      if (uniqueData.length > 0) {
        const mostRecentTimestamp = uniqueData[uniqueData.length - 1].timestamp * 1000;
        const ageMs = Date.now() - mostRecentTimestamp;
        setDataAge(Math.floor(ageMs / 1000));
      }
      
      setData(uniqueData);
      setLastUpdate(new Date());
      setLoading(false);
      setConnectionStatus('connected');
    } catch (err) {
      console.error('Erro ao buscar dados:', err);
      setError(err.message || 'Erro desconhecido ao carregar dados');
      setLoading(false);
      setConnectionStatus('error');
    }
  };

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    fetchData();
  }, [selectedLane]);

  useEffect(() => {
    const interval = setInterval(() => {
      if (connectionStatus === 'connected') {
        fetchData();
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [connectionStatus, selectedLane]);

  const latestData = data.length > 0 ? data[data.length - 1] : null;
  const peakData = data.length > 0 ? data.reduce((max, item) => 
    item.current_cars > max.current_cars ? item : max
  ) : null;
  const averageFlow = data.length > 0 ? Math.round(
    data.reduce((sum, item) => sum + item.current_cars, 0) / data.length
  ) : 0;

  const formatTooltip = (value, name, props) => {
    if (name === 'current_cars') {
      return [`${value} carros`, 'Fluxo Atual'];
    }
    if (name === 'rolling_average') {
      return [`${value} carros`, 'Média Móvel'];
    }
    return [value, name];
  };

  const handleRetry = () => {
    setLoading(true);
    setConnectionStatus('connecting');
    fetchData();
  };

  const handleLaneChange = (newLane) => {
    if (newLane !== selectedLane) {
      setSelectedLane(newLane);
      setLoading(true);
      setData([]);
    }
  };

  const getConnectionStatusColor = () => {
    switch (connectionStatus) {
      case 'connected': return 'text-green-600';
      case 'error': return 'text-red-600';
      default: return 'text-yellow-600';
    }
  };

  const getConnectionStatusText = () => {
    switch (connectionStatus) {
      case 'connected': return 'Conectado';
      case 'error': return 'Erro de conexão';
      default: return 'Conectando...';
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mb-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">
              Dashboard de Fluxo de Tráfego
            </h1>
            <p className="text-gray-600">
              Monitoramento em tempo real - {currentTime.toLocaleString('pt-BR')}
            </p>
            {lastUpdate && (
              <p className="text-sm text-gray-500 mt-1">
                Última atualização: {lastUpdate.toLocaleTimeString('pt-BR')}
              </p>
            )}
            <p className={`text-sm mt-1 ${getConnectionStatusColor()}`}>
              Status: {getConnectionStatusText()}
            </p>
            {dataAge !== null && dataAge > 10 && (
              <p className="text-sm mt-1 text-amber-600">
                ⚠️ Dados com {dataAge}s de idade - podem estar desatualizados
              </p>
            )}
          </div>
          <div className="flex items-center space-x-4">
            <div className="flex items-center">
              <Navigation className="h-4 w-4 text-gray-500 mr-2" />
              <select
                value={selectedLane}
                onChange={(e) => handleLaneChange(e.target.value)}
                className="bg-white border border-gray-300 rounded-lg px-3 py-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {availableLanes.map(lane => (
                  <option key={lane} value={lane}>
                    {lane.replace('_', ' ').toUpperCase()}
                  </option>
                ))}
              </select>
            </div>

            {loading && (
              <div className="flex items-center text-blue-600">
                <Loader className="h-4 w-4 animate-spin mr-2" />
                <span className="text-sm">Atualizando...</span>
              </div>
            )}
            <button
              onClick={handleRetry}
              disabled={loading}
              className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              Atualizar Dados
            </button>
          </div>
        </div>
      </div>

      {error && (
        <ErrorMessage message={error} onRetry={handleRetry} />
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        <StatCard
          icon={Car}
          title="Carros Atuais"
          value={latestData?.current_cars || 0}
          subtitle={`${selectedLane.replace('_', ' ').toUpperCase()} - Agora`}
          color="#3B82F6"
          isLoading={loading && !latestData}
        />
        <StatCard
          icon={TrendingUp}
          title="Média Móvel"
          value={latestData?.rolling_average || '0.0'}
          subtitle="Últimos registros"
          color="#10B981"
          isLoading={loading && !latestData}
        />
        <StatCard
          icon={Clock}
          title="Horário de Pico"
          value={peakData?.hour || '--:--'}
          subtitle={peakData ? `${peakData.current_cars} carros` : 'Sem dados'}
          color="#EF4444"
          isLoading={loading && !peakData}
        />
      </div>

      {data.length > 0 ? (
        <div className="bg-white rounded-lg shadow-lg p-6 mb-8">
          <h2 className="text-xl font-semibold text-gray-900 mb-4 flex items-center">
            <Activity className="mr-2 h-5 w-5 text-blue-500" />
            Fluxo de Carros - {selectedLane.replace('_', ' ').toUpperCase()}
          </h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
              <XAxis 
                dataKey="hour" 
                tick={{ fontSize: 12 }}
                axisLine={{ stroke: '#374151' }}
              />
              <YAxis 
                tick={{ fontSize: 12 }}
                axisLine={{ stroke: '#374151' }}
                label={{ value: 'Número de Carros', angle: -90, position: 'insideLeft' }}
              />
              <Tooltip 
                formatter={formatTooltip}
                labelFormatter={(label) => `Horário: ${label}`}
                labelStyle={{ color: '#374151' }}
                contentStyle={{ 
                  backgroundColor: '#FFFFFF', 
                  border: '1px solid #E5E7EB',
                  borderRadius: '8px'
                }}
              />
              <Line 
                type="monotone" 
                dataKey="current_cars" 
                stroke="#3B82F6" 
                strokeWidth={3}
                dot={{ fill: '#3B82F6', strokeWidth: 2, r: 4 }}
                activeDot={{ r: 6, stroke: '#3B82F6', strokeWidth: 2 }}
                isAnimationActive={false}
              />
              <Line 
                type="monotone" 
                dataKey="rolling_average" 
                stroke="#10B981" 
                strokeWidth={2}
                strokeDasharray="5 5"
                dot={{ fill: '#10B981', strokeWidth: 1, r: 2 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : !loading && (
        <div className="bg-white rounded-lg shadow-lg p-12 text-center mb-8">
          <Car className="h-16 w-16 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-gray-900 mb-2">Nenhum dado disponível</h3>
          <p className="text-gray-600 mb-2">
            Não há dados para {selectedLane.replace('_', ' ').toUpperCase()} no momento.
          </p>
          <p className="text-sm text-gray-500 mb-4">
            {connectionStatus === 'error' 
              ? 'Verifique se a API está rodando em http://192.168.0.3:8080'
              : 'Aguardando dados do sistema de detecção...'
            }
          </p>
          <button
            onClick={handleRetry}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
          >
            Carregar Dados
          </button>
        </div>
      )}

      {data.length > 0 && (
        <div className="bg-white rounded-lg shadow-lg p-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">
            Resumo do Período - {selectedLane.replace('_', ' ').toUpperCase()}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="text-center p-4 bg-blue-50 rounded-lg">
              <p className="text-sm text-gray-600 mb-1">Fluxo Médio</p>
              <p className="text-2xl font-bold text-blue-600">{averageFlow}</p>
              <p className="text-sm text-gray-500">carros por registro</p>
            </div>
            <div className="text-center p-4 bg-green-50 rounded-lg">
              <p className="text-sm text-gray-600 mb-1">Maior Pico</p>
              <p className="text-2xl font-bold text-green-600">{peakData?.current_cars || 0}</p>
              <p className="text-sm text-gray-500">às {peakData?.hour || '--:--'}</p>
            </div>
            <div className="text-center p-4 bg-amber-50 rounded-lg">
              <p className="text-sm text-gray-600 mb-1">Registros</p>
              <p className="text-2xl font-bold text-amber-600">{data.length}</p>
              <p className="text-sm text-gray-500">pontos de dados</p>
            </div>
            <div className="text-center p-4 bg-purple-50 rounded-lg">
              <p className="text-sm text-gray-600 mb-1">Lane Ativa</p>
              <p className="text-2xl font-bold text-purple-600">{selectedLane.replace('_', ' ').toUpperCase()}</p>
              <p className="text-sm text-gray-500">monitoramento ativo</p>
            </div>
          </div>
        </div>
      )}

      {process.env.NODE_ENV === 'development' && data.length > 0 && (
        <div className="mt-6 bg-gray-100 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Debug Info</h3>
          <div className="text-xs text-gray-600 space-y-1">
            <p>Status: {connectionStatus} | Lane: {selectedLane} | Dados: {data.length} registros | Carregando: {loading.toString()}</p>
            <p>Último timestamp: {latestData?.datetime}</p>
            <p>Range de dados: {data[0]?.hour} - {data[data.length - 1]?.hour}</p>
            {error && <p className="text-red-600">Erro: {error}</p>}
          </div>
        </div>
      )}
    </div>
  );
};

export default TrafficDashboard;
