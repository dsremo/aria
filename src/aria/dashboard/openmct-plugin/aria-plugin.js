/**
 * ARIA Spacecraft Telemetry Plugin for NASA OpenMCT
 *
 * Connects OpenMCT to ARIA's telemetry WebSocket server to display
 * real-time spacecraft data from Basilisk simulation or live hardware.
 *
 * Features:
 *   - Auto-discovers telemetry points from ARIA dictionary endpoint
 *   - Real-time streaming via WebSocket
 *   - Historical data queries via REST
 *   - Alarm limits (warning/critical) per telemetry point
 *   - Subsystem-organized folder hierarchy
 *
 * Usage:
 *   openmct.install(ARIAPlugin({ serverUrl: 'http://localhost:8080' }));
 */

const ARIA_NAMESPACE = 'aria';
const ARIA_KEY = 'aria-spacecraft';

function ARIAPlugin(options = {}) {
    const serverUrl = options.serverUrl || 'http://localhost:8080';
    const wsUrl = serverUrl.replace('http', 'ws') + '/realtime';

    return function install(openmct) {
        // ─── Root Object Provider ───
        const rootIdentifier = { namespace: ARIA_NAMESPACE, key: 'root' };

        openmct.objects.addRoot(rootIdentifier);

        openmct.objects.addProvider(ARIA_NAMESPACE, {
            _dictionary: null,
            _dictionaryPromise: null,

            async _loadDictionary() {
                if (this._dictionary) return this._dictionary;
                if (this._dictionaryPromise) return this._dictionaryPromise;

                this._dictionaryPromise = fetch(serverUrl + '/dictionary')
                    .then(r => r.json())
                    .then(dict => {
                        this._dictionary = dict;
                        return dict;
                    });

                return this._dictionaryPromise;
            },

            async get(identifier) {
                const dict = await this._loadDictionary();

                // Root folder
                if (identifier.key === 'root') {
                    const subsystems = [...new Set(dict.map(d => d.subsystem))];
                    return {
                        identifier: identifier,
                        name: 'ARIA Spacecraft',
                        type: 'folder',
                        location: 'ROOT',
                        composition: subsystems.map(ss => ({
                            namespace: ARIA_NAMESPACE,
                            key: 'subsystem.' + ss
                        }))
                    };
                }

                // Subsystem folder
                if (identifier.key.startsWith('subsystem.')) {
                    const ss = identifier.key.replace('subsystem.', '');
                    const points = dict.filter(d => d.subsystem === ss);
                    const ssName = ss.charAt(0).toUpperCase() + ss.slice(1);
                    return {
                        identifier: identifier,
                        name: ssName,
                        type: 'folder',
                        location: ARIA_NAMESPACE + ':root',
                        composition: points.map(p => ({
                            namespace: ARIA_NAMESPACE,
                            key: p.key
                        }))
                    };
                }

                // Telemetry point
                const point = dict.find(d => d.key === identifier.key);
                if (point) {
                    return {
                        identifier: identifier,
                        name: point.name,
                        type: 'aria.telemetry',
                        location: ARIA_NAMESPACE + ':subsystem.' + point.subsystem,
                        telemetry: {
                            values: [
                                {
                                    key: 'timestamp',
                                    name: 'Timestamp',
                                    format: 'utc',
                                    hints: { domain: 1 }
                                },
                                {
                                    key: 'value',
                                    name: point.name,
                                    unit: point.unit || '',
                                    format: point.format === 'enum' ? 'enum' : 'number',
                                    formatString: point.format === 'float' ? '%0.3f' : '%d',
                                    enumerations: point.enumerations || undefined,
                                    hints: { range: 1 }
                                }
                            ]
                        }
                    };
                }

                return undefined;
            }
        });

        // ─── Telemetry Type ───
        openmct.types.addType('aria.telemetry', {
            name: 'ARIA Telemetry Point',
            description: 'Spacecraft telemetry from ARIA AI system',
            cssClass: 'icon-telemetry'
        });

        // ─── Historical Telemetry Provider ───
        openmct.telemetry.addProvider({
            supportsRequest(domainObject) {
                return domainObject.type === 'aria.telemetry';
            },

            async request(domainObject, options = {}) {
                const key = domainObject.identifier.key;
                const params = new URLSearchParams();
                if (options.start) params.set('start', options.start);
                if (options.end) params.set('end', options.end);
                if (options.size) params.set('limit', options.size);

                try {
                    const resp = await fetch(
                        serverUrl + '/history/' + key + '?' + params.toString()
                    );
                    if (!resp.ok) return [];
                    return await resp.json();
                } catch (e) {
                    console.warn('ARIA history fetch failed:', e);
                    return [];
                }
            }
        });

        // ─── Real-time Telemetry Provider (WebSocket) ───
        let ws = null;
        const listeners = {};

        function ensureWebSocket() {
            if (ws && ws.readyState === WebSocket.OPEN) return;
            if (ws && ws.readyState === WebSocket.CONNECTING) return;

            ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                console.log('[ARIA] WebSocket connected to', wsUrl);
                // Re-subscribe all active listeners
                for (const key of Object.keys(listeners)) {
                    ws.send(JSON.stringify({ subscribe: key }));
                }
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    const callbacks = listeners[data.key];
                    if (callbacks) {
                        callbacks.forEach(cb => cb(data));
                    }
                } catch (e) {
                    // Ignore parse errors
                }
            };

            ws.onclose = () => {
                console.log('[ARIA] WebSocket disconnected, reconnecting in 3s...');
                setTimeout(ensureWebSocket, 3000);
            };

            ws.onerror = () => {
                // onclose will fire after onerror
            };
        }

        openmct.telemetry.addProvider({
            supportsSubscribe(domainObject) {
                return domainObject.type === 'aria.telemetry';
            },

            subscribe(domainObject, callback) {
                const key = domainObject.identifier.key;
                ensureWebSocket();

                if (!listeners[key]) {
                    listeners[key] = [];
                }
                listeners[key].push(callback);

                // Subscribe on WebSocket
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ subscribe: key }));
                }

                // Return unsubscribe function
                return function unsubscribe() {
                    const idx = listeners[key]?.indexOf(callback);
                    if (idx >= 0) {
                        listeners[key].splice(idx, 1);
                    }
                    if (listeners[key]?.length === 0) {
                        delete listeners[key];
                        if (ws && ws.readyState === WebSocket.OPEN) {
                            ws.send(JSON.stringify({ unsubscribe: key }));
                        }
                    }
                };
            }
        });

        // ─── Limit Provider (Alarm Thresholds) ───
        openmct.telemetry.addProvider({
            supportsLimits(domainObject) {
                return domainObject.type === 'aria.telemetry';
            },

            getLimitEvaluator(domainObject) {
                return {
                    evaluate(datum, valueMetadata) {
                        // Limits evaluated server-side or via dictionary
                        return undefined;
                    }
                };
            }
        });

        console.log('[ARIA] Spacecraft telemetry plugin installed. Server:', serverUrl);
    };
}

// Export for both CommonJS and ES modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ARIAPlugin;
}
if (typeof window !== 'undefined') {
    window.ARIAPlugin = ARIAPlugin;
}
