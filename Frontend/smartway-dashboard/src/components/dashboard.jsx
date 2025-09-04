import React, { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';
import { Car, TrendingUp, Clock, BarChart3, Activity, AlertCircle, Loader } from 'lucide-react';

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

  // Function to fetch data from API
  const fetchData = async () => {
    try {
      setError(null);
      const response = await fetch('http://localhost:8080/data');
      
      if (!response.ok) {
        throw new Error(`Erro HTTP: ${response.status}`);
      }
      
      const rawData = await response.json();
      
      // Transform the data to match the expected format
      const transformedData = rawData.map((item, index) => {
        const date = new Date(item.timestamp * 1000); // Convert Unix timestamp to Date
        return {
          timestamp: item.timestamp,
          current_cars: Math.round(item.current_cars),
          datetime: date.toISOString(),
          rolling_average: item.rolling_average,
          total_count: Math.round(item.total_count),
          hour: date.toLocaleTimeString('pt-BR', { 
            hour: '2-digit', 
            minute: '2-digit' 
          })
        };
      });

      // Sort by timestamp to ensure chronological order
      transformedData.sort((a, b) => a.timestamp - b.timestamp);
      
      setData(transformedData);
      setLastUpdate(new Date());
      setLoading(false);
    } catch (err) {
      console.error('Erro ao buscar dados:', err);
      setError(err.message || 'Erro desconhecido ao carregar dados');
      setLoading(false);
    }
  };

  // Update current time every second
  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  // Initial data fetch
  useEffect(() => {
    fetchData();
  }, []);

  // Set up periodic data updates (every 30 seconds)
  useEffect(() => {
    const interval = setInterval(() => {
      fetchData();
    }, 30000); // Update every 30 seconds

    return () => clearInterval(interval);
  }, []);

  // Calculate statistics based on current data
  const latestData = data.length > 0 ? data[data.length - 1] : null;
  const peakHour = data.length > 0 ? data.reduce((max, item) => 
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
      return [`${value.toFixed(1)} carros`, 'Média Móvel'];
    }
    return [value, name];
  };

  const handleRetry = () => {
    setLoading(true);
    fetchData();
  };

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      {/* Header */}
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
          </div>
          <div className="flex items-center">
            {loading && (
              <div className="flex items-center text-blue-600 mr-4">
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

      {/* Error Message */}
      {error && (
        <ErrorMessage message={error} onRetry={handleRetry} />
      )}

      {/* Cards de Estatísticas */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <StatCard
          icon={Car}
          title="Carros Atuais"
          value={latestData?.current_cars || 0}
          subtitle="No cruzamento agora"
          color="#3B82F6"
          isLoading={loading && !latestData}
        />
        <StatCard
          icon={TrendingUp}
          title="Média Móvel"
          value={latestData?.rolling_average?.toFixed(1) || '0.0'}
          subtitle="Últimos registros"
          color="#10B981"
          isLoading={loading && !latestData}
        />
        <StatCard
          icon={BarChart3}
          title="Total Acumulado"
          value={latestData?.total_count || 0}
          subtitle="Desde o início"
          color="#F59E0B"
          isLoading={loading && !latestData}
        />
        <StatCard
          icon={Clock}
          title="Horário de Pico"
          value={peakHour?.hour || '--:--'}
          subtitle={peakHour ? `${peakHour.current_cars} carros` : 'Sem dados'}
          color="#EF4444"
          isLoading={loading && !peakHour}
        />
      </div>

      {/* Gráficos */}
      {data.length > 0 ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          {/* Gráfico de Linha - Fluxo ao Longo do Tempo */}
          <div className="bg-white rounded-lg shadow-lg p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4 flex items-center">
              <Activity className="mr-2 h-5 w-5 text-blue-500" />
              Fluxo de Carros ao Longo do Tempo
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
                />
                <Line 
                  type="monotone" 
                  dataKey="rolling_average" 
                  stroke="#10B981" 
                  strokeWidth={2}
                  strokeDasharray="5 5"
                  dot={{ fill: '#10B981', strokeWidth: 1, r: 2 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Gráfico de Área - Total Acumulado */}
          <div className="bg-white rounded-lg shadow-lg p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4 flex items-center">
              <BarChart3 className="mr-2 h-5 w-5 text-amber-500" />
              Total Acumulado de Carros
            </h2>
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={data}>
                <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                <XAxis 
                  dataKey="hour" 
                  tick={{ fontSize: 12 }}
                  axisLine={{ stroke: '#374151' }}
                />
                <YAxis 
                  tick={{ fontSize: 12 }}
                  axisLine={{ stroke: '#374151' }}
                  label={{ value: 'Total Acumulado', angle: -90, position: 'insideLeft' }}
                />
                <Tooltip 
                  formatter={(value) => [`${value} carros`, 'Total Acumulado']}
                  labelStyle={{ color: '#374151' }}
                  contentStyle={{ 
                    backgroundColor: '#FFFFFF', 
                    border: '1px solid #E5E7EB',
                    borderRadius: '8px'
                  }}
                />
                <Area 
                  type="monotone" 
                  dataKey="total_count" 
                  stroke="#F59E0B" 
                  fill="#FEF3C7" 
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : !loading && (
        <div className="bg-white rounded-lg shadow-lg p-12 text-center mb-8">
          <Car className="h-16 w-16 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-gray-900 mb-2">Nenhum dado disponível</h3>
          <p className="text-gray-600 mb-4">
            Não há dados de tráfego para exibir no momento.
          </p>
          <button
            onClick={handleRetry}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
          >
            Carregar Dados
          </button>
        </div>
      )}

      {/* Informações Adicionais */}
      {data.length > 0 && (
        <div className="bg-white rounded-lg shadow-lg p-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">
            Resumo do Período
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="text-center p-4 bg-blue-50 rounded-lg">
              <p className="text-sm text-gray-600 mb-1">Fluxo Médio</p>
              <p className="text-2xl font-bold text-blue-600">{averageFlow}</p>
              <p className="text-sm text-gray-500">carros por registro</p>
            </div>
            <div className="text-center p-4 bg-green-50 rounded-lg">
              <p className="text-sm text-gray-600 mb-1">Maior Pico</p>
              <p className="text-2xl font-bold text-green-600">{peakHour?.current_cars || 0}</p>
              <p className="text-sm text-gray-500">às {peakHour?.hour || '--:--'}</p>
            </div>
            <div className="text-center p-4 bg-amber-50 rounded-lg">
              <p className="text-sm text-gray-600 mb-1">Registros</p>
              <p className="text-2xl font-bold text-amber-600">{data.length}</p>
              <p className="text-sm text-gray-500">pontos de dados</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
