// Weather: condition icons and a compact one-line summary of a forecast.
import { t } from '@/i18n'
import { formatNumber } from './format'
import type { Forecast } from '@/types'

const ICONS: Record<string, string> = {
  'clear-night': 'mdi-weather-night', cloudy: 'mdi-weather-cloudy', exceptional: 'mdi-alert-circle-outline', fog: 'mdi-weather-fog',
  hail: 'mdi-weather-hail', lightning: 'mdi-weather-lightning', 'lightning-rainy': 'mdi-weather-lightning-rainy',
  partlycloudy: 'mdi-weather-partly-cloudy', pouring: 'mdi-weather-pouring', rainy: 'mdi-weather-rainy', snowy: 'mdi-weather-snowy',
  'snowy-rainy': 'mdi-weather-snowy-rainy', sunny: 'mdi-weather-sunny', windy: 'mdi-weather-windy', 'windy-variant': 'mdi-weather-windy-variant',
}

export const conditionIcon = (c: string | undefined | null) => (c && ICONS[c]) || 'mdi-weather-partly-cloudy'
export const conditionLabel = (c: string) => t.weather.conditions[c] ?? c

const round = (n: number) => formatNumber(Math.round(n))

/** "8 to 14 °C · feels 6 to 13 °C · rain 40 % from 15:00 · wind 20 km/h" */
export function forecastParts(f: Forecast): string[] {
  const parts = [t.weather.temp(round(f.temp_min), round(f.temp_max))]
  if (Math.round(f.feels_min) !== Math.round(f.temp_min) || Math.round(f.feels_max) !== Math.round(f.temp_max))
    parts.push(t.weather.feels(round(f.feels_min), round(f.feels_max)))
  if (f.rain_probability >= 10) parts.push(f.rain_from ? t.weather.rainFrom(f.rain_probability, f.rain_from) : t.weather.rain(f.rain_probability))
  if (f.wind_max >= 20) parts.push(t.weather.wind(round(f.wind_max)))
  return parts
}

/** Accepts the loosely typed `weather` object stored on outfits. */
export function asForecast(w: unknown): Forecast | null {
  if (!w || typeof w !== 'object') return null
  const f = w as Partial<Forecast>
  return typeof f.temp_min === 'number' && typeof f.temp_max === 'number' ? (f as Forecast) : null
}
