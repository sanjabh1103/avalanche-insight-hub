import { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Rectangle, useMap } from 'react-leaflet';
import type { LatLngBoundsExpression } from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { DEFAULT_CENTER, DEFAULT_ZOOM } from '@/lib/constants';
import { getRiskColor, type GridCell } from '@/lib/gridUtils';

interface Props {
  cells: GridCell[];
  selectedCell: GridCell | null;
  onCellClick: (cell: GridCell) => void;
}

function MapInvalidator() {
  const map = useMap();
  useEffect(() => {
    setTimeout(() => map.invalidateSize(), 100);
  }, [map]);
  return null;
}

export default function AvalancheMap({ cells, selectedCell, onCellClick }: Props) {
  return (
    <MapContainer
      center={DEFAULT_CENTER}
      zoom={DEFAULT_ZOOM}
      className="h-full w-full z-0"
      zoomControl={true}
    >
      <MapInvalidator />
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
