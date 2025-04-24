import express from 'express';
import fetch from 'node-fetch';
import cors from 'cors';
import { setAccessToken, getRecommendations } from './aiDjService.js';

const app = express();
app.use(cors());
app.use(express.json());

const PORT = 3000;

// 1) /login: ...
app.get('/login', (req, res) => {
  const clientId = '4ab0b09e415d4547b9b2454cd81d3738'; // your clientId
  const redirectUri = 'http://localhost:3000/callback';
  const scopes = 'user-top-read user-read-recently-played';

  const loginUrl = `https://accounts.spotify.com/authorize?response_type=code
    &client_id=${clientId}&scope=${encodeURIComponent(scopes)}
    &redirect_uri=${encodeURIComponent(redirectUri)}`.replace(/\s+/g, '');

  console.log('Redirecting to Spotify login:', loginUrl);
  res.redirect(loginUrl);
});

// 2) /callback: ...
app.get('/callback', async (req, res) => {
  const code = req.query.code;
  const clientId = '4ab0b09e415d4547b9b2454cd81d3738';
  const clientSecret = 'c9b934690fcd48f08005976bb08aa2d8';
  const redirectUri = 'http://localhost:3000/callback';

  console.log('Received code from Spotify:', code);

  const authOptions = {
    method: 'POST',
    headers: {
      Authorization: `Basic ${Buffer.from(`${clientId}:${clientSecret}`).toString('base64')}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      code,
      redirect_uri: redirectUri,
    }),
  };

  try {
    const response = await fetch('https://accounts.spotify.com/api/token', authOptions);
    const data = await response.json();

    if (response.ok && data.access_token) {
      setAccessToken(data.access_token);
      console.log('Scopes returned by Spotify:', data.scope);
      console.log('Access token acquired:', data.access_token);
      res.json({ message: 'Login successful, access token set!' });
    } else {
      console.error('Error fetching access token from Spotify:', data);
      res.status(500).json({ error: 'Failed to get access token', details: data });
    }
  } catch (error) {
    console.error('Error handling Spotify callback:', error);
    res.status(500).json({ error: 'Callback failed', details: error.message });
  }
});

// 3) /recommendations: calls getRecommendations()
app.get('/recommendations', async (req, res) => {
  try {
    const recommendations = await getRecommendations();

    if (Array.isArray(recommendations)) {
      if (recommendations.length > 0) {
        console.log('Returning recommended tracks:', recommendations.length);
        return res.json(recommendations);
      } else {
        console.error('No recommendations returned from Spotify API.');
        return res.status(404).send('No recommendations found');
      }
    }
    // if it's an object with {status, error}, that's a Spotify error
    else if (recommendations && recommendations.error) {
      console.error('Detailed Spotify API Error:', recommendations.error);
      return res.status(recommendations.status || 500).send(recommendations.error);
    } 
    // fallback
    else {
      console.error('Unknown Error: Could not fetch recommendations.');
      return res.status(500).send('Error fetching recommendations');
    }
  } catch (error) {
    console.error('Error in /recommendations endpoint:', error);
    res.status(500).send('Internal Server Error in /recommendations');
  }
});

app.listen(PORT, () => {
  console.log(`Node.js server running on http://localhost:${PORT}`);
});
