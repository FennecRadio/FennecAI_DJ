import fetch from 'node-fetch';

let accessToken = process.env.SPOTIFY_ACCESS_TOKEN || '';

export function setAccessToken(token) {
  accessToken = token;
  console.log('✅ Access token set successfully:', token);
}

export function getAccessToken() {
  return accessToken;
}

export async function getRecommendations() {
  if (!accessToken) {
    console.error('❌ Access token is missing or expired.');
    return null;
  }

  const url = `http://localhost:8000/recommendations?access_token=${accessToken}`;

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('🛑 Recommendation error:', response.status, errorText);
      return null;
    }

    const data = await response.json();
    return data?.recommendations ?? [];
  } catch (err) {
    console.error('🔥 Exception fetching recommendations:', err);
    return null;
  }
}
