import { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Rectangle, useMap } from 'react-leaflet';
import type { LatLngBoundsExpression } from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { getRiskColor, type GridCell } from '@/lib/gridUtils';

interface Props {
  cells: GridCell[];
  selectedCell: GridCell | null;
  onCellClick: (cell: GridCell) => void;
  center: [number, number];
  zoom: number;
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

export default function AvalancheMap({ cells, selectedCell, onCellClick, center, zoom }: Props) {
  return (
    <MapContainer
      center={center}
      zoom={zoom}
      className="h-full w-full z-0"
      zoomControl={true}
      touchZoom={true}
      dragging={true}
    >
      <MapUpdater center={center} zoom={zoom} />
      <TileLayer
        attribution='&copy; <a href="https://carto.com/">CARTO</a>'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
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
    </MapContainer>
  );
}
