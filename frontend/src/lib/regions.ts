import type { Body, Location } from './types'
// Starting bounding boxes (lon_min, lat_min, lon_max, lat_max). User-editable framing aids, NOT data claims.
export const CRS: Record<Body, Location['coordinate_system']> = {
  Earth: 'WGS84_lonlat', Moon: 'Moon_planetocentric_east_180', Mars: 'Mars_planetocentric_east_180',
}
export const PRESETS: Record<Body, Array<{ id: string; label: string; bbox: [number, number, number, number] }>> = {
  Moon: [
    { id: 'moon-taurus-littrow', label: 'Taurus–Littrow valley', bbox: [30.3, 19.7, 31.3, 20.7] },
    { id: 'moon-tycho', label: 'Tycho crater floor', bbox: [-11.9, -43.8, -10.9, -42.8] },
  ],
  Mars: [
    { id: 'mars-jezero', label: 'Jezero crater', bbox: [77.0, 17.9, 78.0, 18.9] },
    { id: 'mars-gale', label: 'Gale crater', bbox: [137.3, -5.9, 138.3, -4.9] },
  ],
  Earth: [
    { id: 'earth-atacama', label: 'Atacama Desert, Chile', bbox: [-69.7, -24.7, -68.7, -23.7] },
    { id: 'earth-dry-valleys', label: 'McMurdo Dry Valleys', bbox: [161.0, -77.9, 162.0, -77.0] },
    { id: 'earth-wadi-rum', label: 'Wadi Rum, Jordan', bbox: [35.1, 29.3, 35.9, 29.9] },
  ],
}
export const bodyAccent: Record<Body, string> = { Earth: '#6f9bb8', Moon: '#b9b0a0', Mars: '#c8642b' }
