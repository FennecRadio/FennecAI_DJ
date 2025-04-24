/*  ──────────────────────────────────────────────────────────────────────────
    Fennec AI DJ – front-end controller  (2025-04-23 / skip-guard + auto-relogin)
    ──────────────────────────────────────────────────────────────────────── */

/////////////////////////////////////////////////////////////////////////////
//  UI ELEMENTS
/////////////////////////////////////////////////////////////////////////////
const statusEl     = document.getElementById('player-status');
const songDisplay  = document.getElementById('song-display');
const likeBtn      = document.getElementById('like');
const dislikeBtn   = document.getElementById('dislike');
const nextBtn      = document.getElementById('next-song');
const getSongsBtn  = document.getElementById('get-songs');
const chatInput    = document.getElementById('chat-input');
const sendChatBtn  = document.getElementById('send-chat');
const chatResponse = document.getElementById('chat-response');
const pauseBtn     = document.getElementById('pause');
const resumeBtn    = document.getElementById('resume');
const volumeSlider = document.getElementById('volume');
const djElm        = document.getElementById('ai-dj');   // animated mascot

/////////////////////////////////////////////////////////////////////////////
//  STATE
/////////////////////////////////////////////////////////////////////////////
let accessToken = null;
let userId      = null;
let player      = null;
let deviceId    = null;
let currentSong = null;
let skipGuard   = false;   // ← suppresses the echo state-changed event

const dislikedSet = new Set(JSON.parse(localStorage.getItem('disliked') || '[]'));

/////////////////////////////////////////////////////////////////////////////
//  AUTH FLOW (token validation + auto-relogin)
/////////////////////////////////////////////////////////////////////////////
function relogin() {
  localStorage.removeItem('spotify_token');
  localStorage.removeItem('user_id');
  fetch('http://localhost:8000/login')
    .then(r => r.json())
    .then(d => (window.location.href = d.url))
    .catch(err => {
      statusEl.textContent = '🚫 Login failed';
      console.error('login fetch error', err);
    });
}

// 1) pull from URL or localStorage
const params = new URLSearchParams(window.location.search);
if (params.has('access_token') && params.has('user_id')) {
  accessToken = params.get('access_token');
  userId      = params.get('user_id');
  localStorage.setItem('spotify_token', accessToken);
  localStorage.setItem('user_id', userId);
  window.history.replaceState({}, document.title, '/');
} else {
  accessToken = localStorage.getItem('spotify_token');
  userId      = localStorage.getItem('user_id');
}

// 2) verify token or relogin
if (!accessToken || !userId) {
  relogin();
} else {
  fetch('https://api.spotify.com/v1/me',
        {headers:{Authorization:`Bearer ${accessToken}`}})
    .then(r => { if (r.status >= 400) relogin(); })
    .catch(relogin);
}

[getSongsBtn, nextBtn, pauseBtn, resumeBtn].forEach(b => (b.disabled = true));

/////////////////////////////////////////////////////////////////////////////
//  SPOTIFY SDK
/////////////////////////////////////////////////////////////////////////////
window.onSpotifyWebPlaybackSDKReady = () => {
  player = new Spotify.Player({
    name: 'Fennec AI DJ Player',
    getOAuthToken: cb => cb(accessToken),
    volume: parseFloat(volumeSlider.value)
  });

  player.addListener('ready', ({ device_id }) => {
    deviceId = device_id;
    statusEl.textContent = '🔊 Connected (Premium)';
    [getSongsBtn, nextBtn, pauseBtn, resumeBtn].forEach(b => (b.disabled = false));
  });

  player.addListener('authentication_error', () => relogin());
  player.addListener('not_ready',            () => (statusEl.textContent = '🛑 Device offline'));
  player.addListener('initialization_error', ({message}) => console.error('Init error',  message));
  player.addListener('account_error',        ({message}) => console.error('Acct error',  message));
  player.addListener('playback_error',       ({message}) => { console.warn('Playback error',message); fetchSong(); });

  // auto-advance when track finishes, but ignore the echo event right after skip
  player.addListener('player_state_changed', st => {
    if (!st) return;
    if (skipGuard) { skipGuard = false; return; }     // swallow one dummy event
    if (st.paused && st.position === 0 && st.duration > 0) fetchSong();
  });

  player.connect().then(ok => { if (!ok) console.warn('⚠️ Player connect failed'); });
};

/////////////////////////////////////////////////////////////////////////////
//  PLAYER CONTROLS
/////////////////////////////////////////////////////////////////////////////
pauseBtn.onclick     = () => player?.pause();
resumeBtn.onclick    = () => player?.resume();
volumeSlider.oninput = e => player?.setVolume(parseFloat(e.target.value));

/////////////////////////////////////////////////////////////////////////////
//  FETCH & PLAY A TRACK
/////////////////////////////////////////////////////////////////////////////
async function fetchSong(attempt = 0) {
  if (!deviceId) { songDisplay.innerText = '❌ Waiting for Spotify device…'; return; }

  try {
    const res = await fetch(
      `http://localhost:8000/recommendations?access_token=${accessToken}&user_id=${encodeURIComponent(userId)}`
    );
    if (res.status === 401) { relogin(); return; }
    if (!res.ok) { console.error('recs error', await res.text()); songDisplay.innerText='❌ Recommendation error.'; return; }

    let recs = (await res.json()).recommendations || [];
    recs = recs.filter(t => !dislikedSet.has(t.id));
    if (!recs.length) { songDisplay.innerText = '🎶 No new tracks.'; return; }

    const track = recs.find(t => t.uri);
    if (!track) { if (attempt<3) return fetchSong(attempt+1); songDisplay.innerText='⚠️ No playable track.'; return; }

    currentSong = track;
    skipGuard = true;                              // suppress the echo
    await playOnSpotify(track.uri);
    displaySong(track);
    djJump();

  } catch (err) {
    console.error('fetchSong error', err);
    songDisplay.innerText = '❌ Could not load songs.';
  }
}

/////////////////////////////////////////////////////////////////////////////
//  PLAY ON SPOTIFY
/////////////////////////////////////////////////////////////////////////////
async function playOnSpotify(uri) {
  await fetch(
    `https://api.spotify.com/v1/me/player/play?device_id=${deviceId}`,
    {
      method:'PUT',
      headers:{'Content-Type':'application/json', Authorization:`Bearer ${accessToken}`},
      body:JSON.stringify({uris:[uri]})
    }
  ).catch(e => { if (e.status===401) relogin(); });
}

/////////////////////////////////////////////////////////////////////////////
//  DISPLAY
/////////////////////////////////////////////////////////////////////////////
function displaySong(song) {
  const artist = song.artists?.[0]?.name ?? 'Unknown';
  const img    = song.album?.images?.[0]?.url ?? '';
  const album  = song.album?.name ?? '';
  songDisplay.innerHTML = `
    <h2>${song.name}</h2>
    <p>${artist}</p>
    ${album && album !== 'Unknown' ? `<p style="opacity:.7">${album}</p>` : ''}
    ${img ? `<img src="${img}" class="album-art" alt="Album art">` : ''}
  `;
}

/////////////////////////////////////////////////////////////////////////////
//  AI DJ  jump helper
/////////////////////////////////////////////////////////////////////////////
function djJump(){
  if (!djElm) return;
  djElm.classList.add('song-change');
  setTimeout(()=>djElm.classList.remove('song-change'),600);
}

/////////////////////////////////////////////////////////////////////////////
//  FLASH
/////////////////////////////////////////////////////////////////////////////
function flash(btn, type){
  const cls = type==='like' ? 'flash-like' : 'flash-dislike';
  btn.classList.add('flash', cls);
  setTimeout(()=>btn.classList.remove('flash', cls), 350);
}

/////////////////////////////////////////////////////////////////////////////
//  FEEDBACK
/////////////////////////////////////////////////////////////////////////////
async function sendFeedback(feedback){
  if (!currentSong) return;
  flash(feedback==='like'?likeBtn:dislikeBtn, feedback);
  fetch('http://localhost:8000/feedback',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({user_id:userId,track_id:currentSong.id,feedback})
  }).catch(console.warn);

  if (feedback==='dislike'){
    dislikedSet.add(currentSong.id);
    localStorage.setItem('disliked', JSON.stringify([...dislikedSet]));
    skipGuard = true;
    fetchSong();
  }
}

/////////////////////////////////////////////////////////////////////////////
//  CHAT COMMANDS
/////////////////////////////////////////////////////////////////////////////
async function sendChatCommand(){
  const msg=chatInput.value.trim(); if(!msg) return;
  chatResponse.innerText='🤖 Thinking…';

  try{
    const res=await fetch('http://localhost:8000/command',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({user_id:userId,message:msg,access_token:accessToken})
    });
    if(res.status===401){relogin();return;}
    const {recommendations}=await res.json();
    if(recommendations?.length){
      const t=recommendations[0];
      skipGuard=true;
      await playOnSpotify(t.uri);
      displaySong(t);
      djJump();
      chatResponse.innerText='✅';
    }else chatResponse.innerText='🤔 No match.';
  }catch(e){
    console.error('chat error',e);
    chatResponse.innerText='❌ Chat error';
  }
  chatInput.value='';
}

/////////////////////////////////////////////////////////////////////////////
//  BINDINGS
/////////////////////////////////////////////////////////////////////////////
getSongsBtn.addEventListener('click', fetchSong);
nextBtn.addEventListener('click', () => { skipGuard=true; fetchSong(); });
likeBtn.addEventListener('click', () => sendFeedback('like'));
dislikeBtn.addEventListener('click', () => sendFeedback('dislike'));
sendChatBtn.addEventListener('click', sendChatCommand);
chatInput.addEventListener('keypress', e => e.key==='Enter' && sendChatCommand());
