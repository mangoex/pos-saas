export interface GpsAddressResult {
  street: string;
  number: string;
  neighborhood: string;
  city: string;
  postalCode: string;
  mapsUrl: string;
  formattedSummary: string;
}

/**
 * Parses reverse geocoding payloads (OpenStreetMap Nominatim or BigDataCloud) into standard address fields.
 */
export function parseReverseGeocodeResponse(data: any, lat: number, lng: number): GpsAddressResult {
  const mapsUrl = `https://maps.google.com/?q=${lat.toFixed(6)},${lng.toFixed(6)}`;

  if (data?.address) {
    const addr = data.address;
    const street = (addr.road || addr.pedestrian || addr.street || addr.footway || addr.path || '').trim();
    const houseNumber = (addr.house_number || '').trim();
    const neighborhood = (addr.neighbourhood || addr.suburb || addr.residential || addr.city_district || addr.quarter || '').trim();
    const city = (addr.city || addr.town || addr.village || addr.municipality || '').trim();
    const postalCode = (addr.postcode || '').trim();

    const summaryParts = [
      street ? (houseNumber ? `${street} #${houseNumber}` : street) : null,
      neighborhood ? `Col. ${neighborhood}` : null,
      city || null,
    ].filter(Boolean);

    return {
      street,
      number: houseNumber,
      neighborhood,
      city,
      postalCode,
      mapsUrl,
      formattedSummary: summaryParts.join(', ') || 'Ubicación GPS detectada',
    };
  }

  // BigDataCloud or generic fallback
  const locality = (data?.locality || data?.city || '').trim();
  const city = (data?.city || data?.principalSubdivision || '').trim();
  const postalCode = (data?.postcode || '').trim();

  return {
    street: '',
    number: '',
    neighborhood: locality,
    city,
    postalCode,
    mapsUrl,
    formattedSummary: locality ? `Cerca de ${locality}` : 'Ubicación GPS detectada',
  };
}

/**
 * Appends GPS satellite pin to delivery references without duplicate links.
 */
export function formatGpsAddressNotes(existingNotes: string, mapsUrl: string): string {
  const trimmed = existingNotes.trim();
  if (trimmed.includes('maps.google.com') || trimmed.includes(mapsUrl)) {
    return trimmed;
  }
  const gpsMarker = `📍 GPS: ${mapsUrl}`;
  if (!trimmed) {
    return gpsMarker;
  }
  return `${trimmed} • ${gpsMarker}`;
}

/**
 * Reverse geocodes coordinates to street and neighborhood with multi-provider fallbacks.
 */
export async function reverseGeocode(
  lat: number,
  lng: number,
  fetchFn: typeof fetch = fetch,
): Promise<GpsAddressResult> {
  const fallbackResult: GpsAddressResult = {
    street: '',
    number: '',
    neighborhood: '',
    city: '',
    postalCode: '',
    mapsUrl: `https://maps.google.com/?q=${lat.toFixed(6)},${lng.toFixed(6)}`,
    formattedSummary: 'Ubicación GPS detectada',
  };

  // 1. Primary provider: OpenStreetMap Nominatim
  try {
    const nominatimUrl = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lng}&accept-language=es`;
    const res = await fetchFn(nominatimUrl, {
      headers: { 'Accept': 'application/json' },
    });
    if (res.ok) {
      const json = await res.json();
      if (json && (json.address || json.display_name)) {
        return parseReverseGeocodeResponse(json, lat, lng);
      }
    }
  } catch (err) {
    // Fallback to secondary provider on error
  }

  // 2. Secondary fallback provider: BigDataCloud Client Reverse Geocode
  try {
    const bdcUrl = `https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${lat}&longitude=${lng}&localityLanguage=es`;
    const res = await fetchFn(bdcUrl);
    if (res.ok) {
      const json = await res.json();
      if (json && (json.locality || json.city)) {
        return parseReverseGeocodeResponse(json, lat, lng);
      }
    }
  } catch (err) {
    // Both failed
  }

  return fallbackResult;
}

/**
 * Obtains current GPS coordinates from the browser's Geolocation API.
 */
export function requestBrowserCoordinates(
  options: PositionOptions = { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
): Promise<{ lat: number; lng: number; accuracy: number }> {
  return new Promise((resolve, reject) => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      return reject(new Error('Tu navegador o dispositivo no soporta geolocalización GPS.'));
    }

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        resolve({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        });
      },
      (err) => {
        let msg = 'No se pudo obtener tu ubicación actual.';
        if (err.code === 1) {
          msg = 'Permiso de ubicación denegado. Puedes ingresar tu dirección manualmente.';
        } else if (err.code === 2) {
          msg = 'Señal GPS no disponible temporalmente. Por favor escribe tu dirección.';
        } else if (err.code === 3) {
          msg = 'Se agotó el tiempo para obtener la señal GPS.';
        }
        reject(new Error(msg));
      },
      options,
    );
  });
}
