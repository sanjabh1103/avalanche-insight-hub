import { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Rectangle, CircleMarker, Popup, useMap } from 'react-leaflet';
import type { LatLngBoundsExpression } from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { getRiskColor, type GridCell } from '@/lib/gridUtils';
import type { AvalancheEvent } from '@/components/HistoricalEventsToggle';
import { useTheme } from 'next-themes';

interface Props {
  cells: GridCell[];
  selectedCell: GridCell | null;
  onCellClick: (cell: GridCell) => void;
  center: [number, number];
  zoom: number;
  historicalEvents?: AvalancheEvent[];
}

function MapUpdater({ center, zoom }: { center: [number, number]; zoom: number }) {
  const map = useMap();
  const prevCenter = useRef(center);
  
  useEffect(() => {
    if (prevCenter.current[0] !== center[0] || prevCenter.current[1] !== center[1]) {
      map.flyTo(center, zoom, { duration: 1.5 });
      prevCenter.current = center;
    }
    setTimeout(() => map.invalidateSize(), 100);
  }, [map, center, zoom]);
  
  return null;
}

function confidenceColor(confidence: number): string {
  if (confidence >= 0.8) return '#ef4444';
  if (confidence >= 0.6) return '#f97316';
  if (confidence >= 0.4) return '#eab308';
  return '#84cc16';
}

export default function AvalancheMap({ cells, selectedCell, onCellClick, center, zoom, historicalEvents = [] }: Props) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme !== 'light';
  const tileUrl = isDark
    ? 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
    : 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';

  return (
    <MapContainer
      center={center}
      zoom={zoom}
      className="h-full w-full z-0 theme-aware-map"
      zoomControl={true}
      touchZoom={true}
      dragging={true}
    >
      <MapUpdater center={center} zoom={zoom} />
      <TileLayer
        attribution='&copy; <a href="https://carto.com/">CARTO</a>'
        url={tileUrl}
      />
      {cells.map((cell) => {
        const bounds: LatLngBoundsExpression = [
          [cell.lat, cell.lng],
          [cell.latEnd, cell.lngEnd],
        ];
        const isSelected =
          selectedCell?.row === cell.row && selectedCell?.col === cell.col;
        return (
          <Rectangle
            key={`${cell.row}-${cell.col}`}
            bounds={bounds}
            pathOptions={{
              color: isSelected ? '#ffffff' : 'transparent',
              weight: isSelected ? 2 : 0,
              fillColor: getRiskColor(cell.riskScore),
              fillOpacity: 0.45 + cell.riskScore * 0.06,
            }}
            eventHandlers={{
              click: () => onCellClick(cell),
            }}
          />
        );
      })}
      {historicalEvents.map((evt) => (
        <CircleMarker
          key={evt.id}
          center={[evt.lat, evt.lng]}
          radius={8}
          pathOptions={{
            color: confidenceColor(evt.confidence),
            fillColor: confidenceColor(evt.confidence),
            fillOpacity: 0.7,
            weight: 2,
          }}
        >
          <Popup>
            <div
              className="text-xs space-y-1"
              style={{ color: isDark ? '#ddd' : '#111' }}
            >
              <div className="font-bold">{evt.event_type.toUpperCase()}</div>
              <div>{evt.description}</div>
              <div className={isDark ? 'text-gray-400' : 'text-gray-600'}>
                Source: {evt.source} • Confidence: {(evt.confidence * 100).toFixed(0)}%
              </div>
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
