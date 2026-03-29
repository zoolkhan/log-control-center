const CONFIG = {
    mapDataUrl: 'world.geojson',
    homeCoords: { lat: 60.6875, lon: 23.4583 },
    refreshRate: 5000,
    pskRefreshRate: 60000,
    myCall: 'OH8XAT'
};
let worldData = null;
let lastHeartbeat = null;
let heartbeatFailCount = 0;
let propagationText = "[AWAITING DATA]";
let pskSpots = [];
let isPskActive = false;
let pskSeconds = 0;

const GLOBAL_CALL_CACHE = {};
const PREFIX_MAP = {'DL':[51,10],'F':[46,2],'G':[54,-2],'M':[54,-2],'K':[37,-95],'W':[37,-95],'OH':[64,26],'LA':[60,10],'SM':[60,15],'OZ':[56,10],'UR':[49,31],'UA':[55,37],'4Z':[31,35],'4X':[32,34],'ES':[58,25],'YL':[56,24],'LY':[55,23],'SP':[52,19],'OK':[49,14],'OM':[48,19],'HA':[47,19],'S5':[46,14],'YU':[44,20],'LZ':[42,25],'SV':[38,23],'EA':[40,-3],'I':[41,12],'HB':[46,8],'OE':[47,14],'PA':[52,5],'ON':[50,4]};

const escapeRegExp = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const getDist = (lat1, lon1, lat2, lon2) => {
    const R = 6371;
    const dLat = (lat2-lat1) * Math.PI / 180;
    const dLon = (lon2-lon1) * Math.PI / 180;
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon/2) * Math.sin(dLon/2);
    return Math.round(R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a)));
};

const getBearing = (lat1, lon1, lat2, lon2) => {
    const l1 = lat1 * Math.PI / 180;
    const l2 = lat2 * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const y = Math.sin(dLon) * Math.cos(l2);
    const x = Math.cos(l1) * Math.sin(l2) - Math.sin(l1) * Math.cos(l2) * Math.cos(dLon);
    let brng = Math.atan2(y, x) * 180 / Math.PI;
    return Math.round((brng + 360) % 360);
};

const maidenheadToLatLon = (g) => {
    if(!g || g.length < 4) return null;
    g = g.toUpperCase();
    let lon = (g.charCodeAt(0) - 65) * 20 - 180;
    let lat = (g.charCodeAt(1) - 65) * 10 - 90;
    lon += parseInt(g[2]) * 2;
    lat += parseInt(g[3]);
    if (g.length >= 6) {
        lon += (g.charCodeAt(4) - 65) * (2 / 24);
        lat += (g.charCodeAt(5) - 65) * (1 / 24);
        lon += (1 / 24);
        lat += (0.5 / 24);
    } else {
        lon += 1;
        lat += 0.5;
    }
    return {lat, lon};
};

class BridgeMonitor {
    constructor(id, sourcePath, color, type = 'adif') {
        this.id = id; this.sourcePath = sourcePath; this.color = color;
        this.type = type; this.logs = []; this.isFilterActive = false; this.isZoomActive = true;
        this.canvas = document.getElementById('map-' + id);
        this.feed = document.getElementById('log-feed-' + id);
        this.limitSelect = document.getElementById('limit-' + id);
        this.filterBtn = document.getElementById('filter-' + id);
        this.zoomBtn = document.getElementById('zoom-' + id);
        this.lastRawLine = null;
        
        if(this.filterBtn) this.filterBtn.onclick = () => { this.isFilterActive = !this.isFilterActive; this.filterBtn.innerText = 'FILTER: ' + (this.isFilterActive ? 'ON' : 'OFF'); this.updateFeed(); };
        if(this.zoomBtn) this.zoomBtn.onclick = () => { this.isZoomActive = !this.isZoomActive; this.zoomBtn.innerText = 'ZOOM: ' + (this.isZoomActive ? 'ON' : 'OFF'); this.draw(); };
    }
    parse(text) {
        if (!text) return [];
        if (this.type === 'adif') {
            return text.split(/<EOR>/i).filter(e=>e.trim()).map(e=>{const o={};const r=/<([^:>]+):(\d+)>([^<]*)/gi;let m;while((m=r.exec(e))!==null){o[m[1].toUpperCase()]=m[3].trim();}
                if(o.CALL && o.GRIDSQUARE) GLOBAL_CALL_CACHE[o.CALL] = o.GRIDSQUARE;
                return o;
            }).filter(o=>o.CALL).sort((a,b)=>((a.QSO_DATE||'0')+(a.TIME_ON||'0')).localeCompare(((b.QSO_DATE||'0')+(b.TIME_ON||'0'))));
        } else {
            return text.split('\n').filter(l=>l.trim()).map(l=>{
                const mCall = l.match(/from\s+([A-Z0-9\/]+)/) || l.match(/\(([A-Z0-9\/]+)\)/) || l.match(/\b([A-Z0-9]{1,3}[0-9][A-Z]{1,3})\b/);
                const mGrid = l.match(/\(([A-Z]{2}[0-9]{2}[A-Z]{0,2})\)/);
                const o = {raw:l, CALL:mCall?mCall[1]:null, GRIDSQUARE:mGrid?mGrid[1]:null};
                if(o.CALL && o.GRIDSQUARE) GLOBAL_CALL_CACHE[o.CALL] = o.GRIDSQUARE;
                return o;
            });
        }
    }
    getCoords(log) {
        let g = log.GRIDSQUARE;
        if(!g && log.CALL) g = GLOBAL_CALL_CACHE[log.CALL];
        if(g) return maidenheadToLatLon(g);
        if(log.CALL){
            const p=PREFIX_MAP[log.CALL.slice(0,2)]||PREFIX_MAP[log.CALL.slice(0,1)];
            if(p)return{lat:p[0],lon:p[1]};
        }
        return null;
    }
    draw() {
        if (!this.canvas || !worldData) return;
        const ctx = this.canvas.getContext('2d');
        const parent = this.canvas.parentElement;

        const latest = this.logs.filter(l=>l.CALL && this.getCoords(l)).pop();
        const latestCoords = latest ? this.getCoords(latest) : null;

        // Dynamic Tactical Layout arrangement
        if (latestCoords && this.id === 'a') {
            const latDiff = Math.abs(latestCoords.lat - CONFIG.homeCoords.lat);
            const lonDiff = Math.abs(latestCoords.lon - CONFIG.homeCoords.lon);
            const tacticalSection = document.querySelector('.tactical-monitor .split-v') || document.querySelector('.tactical-monitor .split-h');
            if (tacticalSection) {
                // If horizontal (lon) diff is much larger than vertical (lat), or if it's generally East-West (e.g. USA)
                // we prefer vertical stacking (maps above each other) to get more side-to-side real estate.
                if (lonDiff > 45 || lonDiff > latDiff * 1.5) {
                    tacticalSection.className = 'split-h';
                } else {
                    tacticalSection.className = 'split-v';
                }
            }
        }

        if(this.canvas.width !== parent.offsetWidth) this.canvas.width = parent.offsetWidth;
        if(this.canvas.height !== parent.offsetHeight) this.canvas.height = parent.offsetHeight;
        ctx.clearRect(0,0,this.canvas.width,this.canvas.height);
        ctx.setLineDash([]);
        
        let minLat = -90, maxLat = 90, minLon = -180, maxLon = 180;
        if(this.isZoomActive && latestCoords) {
            const padding = 10;
            minLat = Math.min(CONFIG.homeCoords.lat, latestCoords.lat) - padding;
            maxLat = Math.max(CONFIG.homeCoords.lat, latestCoords.lat) + padding;
            minLon = Math.min(CONFIG.homeCoords.lon, latestCoords.lon) - padding;
            maxLon = Math.max(CONFIG.homeCoords.lon, latestCoords.lon) + padding;
            const latRange = maxLat - minLat; const lonRange = maxLon - minLon;
            const canvasRatio = this.canvas.width / this.canvas.height;
            const dataRatio = lonRange / latRange;
            if (dataRatio > canvasRatio) { const targetLatRange = lonRange / canvasRatio; const diff = targetLatRange - latRange; minLat -= diff/2; maxLat += diff/2; }
            else { const targetLonRange = latRange * canvasRatio; const diff = targetLonRange - lonRange; minLon -= diff/2; maxLon += diff/2; }
        } else {
            const canvasRatio = this.canvas.width / this.canvas.height;
            if (canvasRatio > 2) { const targetLonRange = 180 * canvasRatio; minLon = -targetLonRange/2; maxLon = targetLonRange/2; }
            else { const targetLatRange = 360 / canvasRatio; minLat = -targetLatRange/2; maxLat = targetLatRange/2; }
        }

        const pr = (la,lo)=>({x:(lo - minLon) * (this.canvas.width / (maxLon - minLon)), y:(maxLat - la) * (this.canvas.height / (maxLat - minLat))});
        ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--accent-dim').trim() + '88'; 
        ctx.lineWidth = 2;
        worldData.features.forEach(f=>{const dr=(p)=>{ctx.beginPath();p.forEach((c,i)=>{const pos=pr(c[1],c[0]);if(i===0)ctx.moveTo(pos.x,pos.y);else ctx.lineTo(pos.x,pos.y);});ctx.stroke();};if(f.geometry.type==='Polygon')dr(f.geometry.coordinates[0]);else f.geometry.coordinates.forEach(poly=>dr(poly[0]));});
        
        const h = pr(CONFIG.homeCoords.lat, CONFIG.homeCoords.lon);
        ctx.fillStyle='#ff6600';ctx.beginPath();ctx.arc(h.x,h.y,4,0,Math.PI*2);ctx.fill();

        if(isPskActive && pskSpots.length > 0) {
            pskSpots.forEach(s => {
                const c = maidenheadToLatLon(s.locator);
                if(!c) return;
                const p2 = pr(c.lat, c.lon);
                ctx.strokeStyle = '#ff00ff44'; ctx.lineWidth = 1;
                ctx.beginPath(); ctx.moveTo(h.x, h.y); ctx.lineTo(p2.x, p2.y); ctx.stroke();
                ctx.fillStyle = '#ff00ff88'; ctx.beginPath(); ctx.arc(p2.x, p2.y, 2, 0, Math.PI*2); ctx.fill();
            });
        }

        const limit = this.limitSelect ? parseInt(this.limitSelect.value) : 5;
        const contacts = this.logs.filter(l=>l.CALL && this.getCoords(l)).slice(-limit);
        contacts.forEach((l, idx) => {
            const isLatest = idx === contacts.length - 1;
            const c = this.getCoords(l);
            const p2 = pr(c.lat, c.lon);
            ctx.strokeStyle = isLatest ? this.color : '#00ff6677';
            ctx.lineWidth = isLatest ? 3 : 1;
            ctx.setLineDash(isLatest ? [] : [4, 4]);
            ctx.beginPath(); ctx.moveTo(h.x,h.y); ctx.lineTo(p2.x,p2.y); ctx.stroke();
            ctx.setLineDash([]);
            ctx.fillStyle = isLatest ? this.color : '#00ff6677';
            ctx.beginPath(); ctx.arc(p2.x,p2.y, isLatest ? 5 : 2, 0, Math.PI*2); ctx.fill();
            if(isLatest) {
                const dist = getDist(CONFIG.homeCoords.lat, CONFIG.homeCoords.lon, c.lat, c.lon);
                const az = getBearing(CONFIG.homeCoords.lat, CONFIG.homeCoords.lon, c.lat, c.lon);
                let grid = l.GRIDSQUARE || (l.CALL ? GLOBAL_CALL_CACHE[l.CALL] : null);
                ctx.font = 'bold 12px Monospace'; ctx.fillStyle = '#fff';
                ctx.fillText(l.CALL + ' (' + dist + 'KM ' + az + '°)', p2.x + 8, p2.y + 4);
                if(grid) {
                    ctx.font = '10px Monospace'; ctx.fillStyle = '#00f2ff';
                    ctx.fillText(grid, p2.x + 8, p2.y + 16);
                    ctx.strokeStyle = '#00f2ffaa'; ctx.lineWidth = 1; ctx.strokeRect(p2.x - 6, p2.y - 6, 12, 12);
                }
            }
        });
    }
    updateFeed() {
        if(!this.feed)return;
        let displayLogs = this.logs.slice().reverse();
        if(this.isFilterActive) displayLogs = displayLogs.filter(l => !l.raw || (!l.raw.includes('Sending beacon') && !l.raw.includes('KISS BEACON sent')));
        const newHtml = displayLogs.slice(0,50).map((l,i)=>{
            const fD=(d)=>(d&&d.length===8)?d.slice(0,4)+'-'+d.slice(4,6)+'-'+d.slice(6,8):d;
            const fT=(t)=>(t&&t.length>=4)?t.slice(0,2)+':'+t.slice(2,4):t;
            let color = (i===0 && l.CALL) ? this.color : (l.CALL?'#00ff66':'#888');
            let extraClass = (i===0 && l.CALL && this.id === 'a') ? ' deck-a-latest' : '';
            
            if(this.type==='adif') return '<div class="log-entry' + extraClass + '" style="color:'+color+'"><span>'+fD(l.QSO_DATE)+' '+fT(l.TIME_ON)+'</span><span>'+l.CALL+'</span><span>'+(l.BAND||'')+'</span><span>'+(l.SUBMODE||l.MODE||'')+'</span></div>';
            else {
                let txt = l.raw.replace(/[a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+\.[a-zA-Z0-9_-]+/g, m => m.charAt(0) + '***@' + m.split('@')[1]);
                if(l.CALL) {
                    const regex = new RegExp('(\\()?'+escapeRegExp(l.CALL)+'(\\))?', 'g');
                    const highlightClass = this.id === 'a' ? 'callsign-highlight-a' : 'callsign-highlight-b';
                    txt = txt.replace(regex, (m, p1, p2) => (p1||'') + '<span class="' + highlightClass + '">' + l.CALL + '</span>' + (p2||''));
                }
                return '<div class="log-entry" style="color:'+color+'"><span style="grid-column:span 4">'+txt+'</span></div>';
            }
        }).join('');
        if(this.feed.innerHTML !== newHtml) this.feed.innerHTML = newHtml;
    }
    async refresh(bootstrapText = null) {
        try {
            let t = bootstrapText;
            if(!t) {
                const r = await fetch(this.sourcePath+'?t='+Date.now());
                if (!r.ok) return;
                t = await r.text();
            }
            const newLogs = this.parse(t);
            if (JSON.stringify(newLogs) !== JSON.stringify(this.logs)) {
                const isInitial = this.logs.length === 0;
                let isNewContact = false; let isBeaconReceived = false;
                if(!isInitial) {
                    if(this.type === 'adif') { isNewContact = newLogs.length > this.logs.length || (newLogs.length > 0 && newLogs[newLogs.length-1].CALL !== this.logs[this.logs.length-1].CALL); }
                    else if(this.type === 'raw' && newLogs.length > 0) {
                        const latestLine = newLogs[newLogs.length-1].raw;
                        if(latestLine !== this.lastRawLine) { if(latestLine.includes('KISS BEACON received')) isBeaconReceived = true; this.lastRawLine = latestLine; }
                    }
                } else if(this.type === 'raw' && newLogs.length > 0) { this.lastRawLine = newLogs[newLogs.length-1].raw; }
                this.logs = newLogs; this.updateFeed(); this.draw();
                if(!isInitial) {
                    const container = this.feed.closest('.monitor');
                    if(container) { container.classList.add('monitor-flash'); setTimeout(()=>container.classList.remove('monitor-flash'), 1500); }
                    if(isNewContact && this.id === 'a') { audio.ping(660, 0.3); }
                    if(isBeaconReceived && this.id === 'b') { audio.chirp(); }
                }
            }
        } catch(e){}
    }
}

class BridgeAudio {
    constructor() {
        this.ctx = null; this.isMuted = true; this.hum = null;
        this.btn = document.getElementById('audio-toggle');
        if(this.btn) this.btn.onclick = () => { this.toggle(); };
    }
    init() {
        if(this.ctx) return;
        this.ctx = new (window.AudioContext || window.webkitAudioContext)();
        this.hum = this.ctx.createOscillator(); const g = this.ctx.createGain();
        this.hum.type = 'sawtooth'; this.hum.frequency.setValueAtTime(40, this.ctx.currentTime);
        g.gain.setValueAtTime(0.01, this.ctx.currentTime);
        const lpf = this.ctx.createBiquadFilter(); lpf.type = 'lowpass'; lpf.frequency.value = 100;
        this.hum.connect(lpf).connect(g).connect(this.ctx.destination);
        this.hum.start(); this.ping(880, 0.1); setTimeout(()=>this.ping(440, 0.1), 100);
    }
    toggle() {
        if(!this.ctx) this.init();
        this.isMuted = !this.isMuted;
        if (this.ctx.state === 'suspended') this.ctx.resume();
        if(this.hum) this.hum.frequency.setTargetAtTime(this.isMuted ? 0 : 40, this.ctx.currentTime, 0.1);
        if(this.btn) { this.btn.innerText = 'AUDIO: ' + (this.isMuted ? 'OFF' : 'ON'); this.btn.style.borderColor = this.isMuted ? 'var(--accent-dim)' : 'var(--accent-color)'; }
    }
    ping(freq = 440, duration = 0.2) {
        if(!this.ctx || this.isMuted) return;
        if (this.ctx.state === 'suspended') this.ctx.resume();
        const o = this.ctx.createOscillator(); const g = this.ctx.createGain();
        o.type = 'triangle'; o.frequency.setValueAtTime(freq, this.ctx.currentTime);
        g.gain.setValueAtTime(0.4, this.ctx.currentTime);
        g.gain.exponentialRampToValueAtTime(0.00001, this.ctx.currentTime + duration);
        o.connect(g).connect(this.ctx.destination); o.start(); o.stop(this.ctx.currentTime + duration);
    }
    chirp() { if(!this.ctx || this.isMuted) return; this.ping(1200, 0.08); setTimeout(() => this.ping(1500, 0.08), 80); }
}

const audio = new BridgeAudio();
const deckA = new BridgeMonitor('a', 'data/source_a.adi', '#ff6600', 'adif');
const deckB = new BridgeMonitor('b', 'data/source_b.log', '#00f2ff', 'raw');

async function refreshPropagation() {
    try {
        const r = await fetch('data/propagation.txt?t='+Date.now());
        if(r.ok) { const t = await r.text(); propagationText = t.replace(/\n/g, ' | ').replace(/\r/g, '').trim(); updateFooter(); }
    } catch(e){}
}

async function refreshHeartbeat() {
    try {
        const r = await fetch('data/heartbeat.json?t='+Date.now());
        if(r.ok) { const data = await r.json(); lastHeartbeat = data.last_seen; heartbeatFailCount = 0; } else { heartbeatFailCount++; }
    } catch(e){ heartbeatFailCount++; }
    updateFooter();
}

async function refreshPsk() {
    if(!isPskActive) return;
    try {
        const r = await fetch('psk_proxy?call=' + CONFIG.myCall + '&seconds=' + pskSeconds + '&t=' + Date.now());
        if(!r.ok) return;
        const text = await r.text();
        const parser = new DOMParser();
        const xml = parser.parseFromString(text, "application/xml");
        const reports = xml.querySelectorAll('receptionReport');
        pskSpots = Array.from(reports).map(node => ({
            callsign: node.getAttribute('receiverCallsign'),
            locator: node.getAttribute('receiverLocator')
        }));
        deckA.draw(); deckB.draw();
    } catch(e) {}
}

function updateFooter() {
    const footer = document.querySelector('.scrolling-text');
    if(!footer) return;
    let statusPrefix = ""; let isOffline = false;
    if(heartbeatFailCount > 3) { statusPrefix = "<span style='color:#ff3c00; font-weight:bold;'>[STATION LINK OFFLINE - DATA UNREACHABLE]</span> "; isOffline = true; } 
    else if(lastHeartbeat) {
        const lastSeen = new Date(lastHeartbeat.replace(' UTC', 'Z'));
        const now = new Date(); const diffSeconds = (now - lastSeen) / 1000;
        if(diffSeconds > 120) { const timeStr = lastHeartbeat.split(' ')[1]; statusPrefix = "<span style='color:#ff3c00; font-weight:bold;'>[STATION LINK OFFLINE SINCE " + timeStr + " UTC]</span> "; isOffline = true; }
    }
    if(isOffline) footer.style.textShadow = "0 0 10px #ff3c00"; else footer.style.textShadow = "none";
    footer.innerHTML = statusPrefix + "[PROPAGATION DATA] " + propagationText;
}

async function init() {
    console.log("BRIDGE: Initializing Data Refresh...");
    deckA.refresh(); deckB.refresh(); refreshPropagation(); refreshHeartbeat(); refreshPsk();

    console.log("BRIDGE: Loading Map Data from " + CONFIG.mapDataUrl);
    fetch(CONFIG.mapDataUrl)
        .then(r => {
            if (!r.ok) throw new Error("HTTP Error " + r.status);
            return r.json();
        })
        .then(data => {
            console.log("BRIDGE: Map Data Loaded Successfully (" + data.features.length + " features)");
            worldData = data; 
            // Force an immediate draw now that we have data
            deckA.draw(); deckB.draw();
            
            setInterval(() => {
                deckA.refresh(); deckB.refresh(); refreshPropagation(); refreshHeartbeat();
            }, CONFIG.refreshRate);
            setInterval(refreshPsk, CONFIG.pskRefreshRate);
        })
        .catch(e => {
            console.error("BRIDGE: Map Data Failure:", e);
            // Fallback: still refresh logs even if map fails
            setInterval(() => {
                deckA.refresh(); deckB.refresh(); refreshPropagation(); refreshHeartbeat();
            }, CONFIG.refreshRate);
        });
}
init();
setInterval(()=>{const c=document.getElementById('current-time');if(c)c.innerText=new Date().toUTCString().split(' ')[4]+' UTC';},1000);
window.onresize=()=>{deckA.draw();deckB.draw();};

const sizeBtn = document.getElementById('size-toggle');
if(sizeBtn) {
    sizeBtn.onclick = () => {
        const isLarge = document.body.classList.toggle('large-font');
        sizeBtn.innerText = 'SIZE: ' + (isLarge ? 'LARGE' : 'NORMAL');
        sizeBtn.style.borderColor = isLarge ? 'var(--accent-color)' : 'var(--accent-dim)';
        deckA.draw(); deckB.draw();
    };
}

const pskLimit = document.getElementById('psk-limit');
if(pskLimit) {
    pskLimit.onchange = () => {
        pskSeconds = parseInt(pskLimit.value);
        isPskActive = pskSeconds > 0;
        if(isPskActive) { pskLimit.style.borderColor = '#ff00ff'; refreshPsk(); }
        else { pskLimit.style.borderColor = 'var(--accent-dim)'; pskSpots = []; deckA.draw(); deckB.draw(); }
    };
}
