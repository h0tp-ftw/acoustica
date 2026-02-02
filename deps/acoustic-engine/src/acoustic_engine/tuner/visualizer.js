/**
 * Visualizer - Handles drawing audiogram, frequency timeline, and event timelines.
 * Features: Interactive hover tooltips, zoom, crop selection, playhead sync.
 * Uses Catppuccin Mocha color palette for cohesive aesthetics.
 */

class Visualizer {
    constructor(audiogramCanvas, frequencyTimelineCanvas, eventsCanvas) {
        this.audiogramCtx = audiogramCanvas.getContext('2d');
        this.frequencyTimelineCtx = frequencyTimelineCanvas.getContext('2d');
        this.eventsCtx = eventsCanvas.getContext('2d');
        
        this.audiogramCanvas = audiogramCanvas;
        this.frequencyTimelineCanvas = frequencyTimelineCanvas;
        this.eventsCanvas = eventsCanvas;
        
        // Detected events for display
        this.detectedEvents = [];
        
        // Zoom state for frequency timeline
        this.zoom = 1.0;
        this.maxZoom = 10.0;
        
        // Crop selection state
        this.cropSelection = null;  // { start: seconds, end: seconds }
        this.isDragging = false;
        this.dragStart = null;
        
        // Cached analysis data for interaction
        this.cachedAnalysis = null;
        
        // Catppuccin Mocha color palette
        this.colors = {
            // Canvas backgrounds
            bg: '#11111b',          // crust
            bgAlt: '#181825',       // mantle
            
            // Audiogram
            audiogram: '#cba6f7',    // mauve
            audiogramFill: 'rgba(203, 166, 247, 0.3)',
            audiogramGlow: 'rgba(203, 166, 247, 0.4)',
            
            // Frequency timeline colors
            freqColors: [
                '#a6e3a1',  // green - primary peak
                '#89b4fa',  // blue - secondary peak
                '#fab387',  // peach - tertiary peak
            ],
            freqLow: '#45475a',     // Low activity
            freqHigh: '#f5c2e7',    // High activity
            
            // Events
            eventTone: '#a6e3a1',   // green
            eventToneAlt: '#94e2d5', // teal
            eventSilence: '#45475a', // surface1
            
            // Selection
            selection: 'rgba(250, 179, 135, 0.3)',  // peach with alpha
            selectionBorder: '#fab387',
            
            // Text and grid
            text: '#a6adc8',        // subtext0
            textBright: '#cdd6f4',  // text
            grid: '#45475a',        // surface1
            gridSubtle: '#313244',  // surface0
            
            // Accents
            accent: '#89b4fa',      // blue
            accentAlt: '#74c7ec',   // sapphire
            pink: '#f5c2e7',
            peach: '#fab387',
            yellow: '#f9e2af',
            red: '#f38ba8'
        };
    }

    /**
     * Draw the audiogram (amplitude envelope over time)
     * @param {Object} analysisData - Frequency analysis data containing timeline with RMS values
     * @param {number} playheadProgress - Optional 0-1 value for playhead position
     */
    drawAudiogram(analysisData, playheadProgress = null) {
        const ctx = this.audiogramCtx;
        const width = this.audiogramCanvas.width;
        const height = this.audiogramCanvas.height;
        
        // Clear with gradient background
        const bgGrad = ctx.createLinearGradient(0, 0, 0, height);
        bgGrad.addColorStop(0, this.colors.bg);
        bgGrad.addColorStop(1, this.colors.bgAlt);
        ctx.fillStyle = bgGrad;
        ctx.fillRect(0, 0, width, height);
        
        if (!analysisData || !analysisData.timeline || analysisData.timeline.length === 0) {
            ctx.fillStyle = this.colors.text;
            ctx.font = '500 11px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('Record or upload audio to see audiogram', width / 2, height / 2);
            return;
        }
        
        const { timeline, totalDuration } = analysisData;
        const pixelsPerSecond = width / totalDuration;
        
        // Find max RMS for normalization
        const maxRms = Math.max(...timeline.map(f => f.rms), 0.01);
        
        // Draw selection region if exists
        if (this.cropSelection) {
            const selStart = this.cropSelection.start * pixelsPerSecond;
            const selEnd = this.cropSelection.end * pixelsPerSecond;
            
            ctx.fillStyle = this.colors.selection;
            ctx.fillRect(selStart, 0, selEnd - selStart, height);
            
            ctx.strokeStyle = this.colors.selectionBorder;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(selStart, 0);
            ctx.lineTo(selStart, height);
            ctx.moveTo(selEnd, 0);
            ctx.lineTo(selEnd, height);
            ctx.stroke();
        }
        
        // Draw audiogram waveform
        ctx.beginPath();
        ctx.moveTo(0, height / 2);
        
        for (const frame of timeline) {
            const x = frame.time * pixelsPerSecond;
            const amplitude = (frame.rms / maxRms) * (height / 2 - 4);
            
            // Draw both positive and negative for waveform look
            ctx.lineTo(x, height / 2 - amplitude);
        }
        
        // Complete the path going back
        for (let i = timeline.length - 1; i >= 0; i--) {
            const frame = timeline[i];
            const x = frame.time * pixelsPerSecond;
            const amplitude = (frame.rms / maxRms) * (height / 2 - 4);
            ctx.lineTo(x, height / 2 + amplitude);
        }
        
        ctx.closePath();
        ctx.fillStyle = this.colors.audiogramFill;
        ctx.fill();
        
        // Draw center line with glow
        ctx.strokeStyle = this.colors.audiogram;
        ctx.lineWidth = 1.5;
        ctx.shadowColor = this.colors.audiogramGlow;
        ctx.shadowBlur = 6;
        
        ctx.beginPath();
        for (let i = 0; i < timeline.length; i++) {
            const frame = timeline[i];
            const x = frame.time * pixelsPerSecond;
            const amplitude = (frame.rms / maxRms) * (height / 2 - 4);
            
            if (i === 0) {
                ctx.moveTo(x, height / 2 - amplitude);
            } else {
                ctx.lineTo(x, height / 2 - amplitude);
            }
        }
        ctx.stroke();
        ctx.shadowBlur = 0;
        
        // Draw time markers
        ctx.fillStyle = this.colors.text;
        ctx.font = '500 9px Inter, sans-serif';
        ctx.textAlign = 'center';
        
        const interval = this._getNiceInterval(totalDuration);
        for (let t = 0; t <= totalDuration; t += interval) {
            const x = t * pixelsPerSecond;
            const label = t.toFixed(1) + 's';
            ctx.fillText(label, x, height - 4);
        }
        
        // Draw playhead if provided
        if (playheadProgress !== null && playheadProgress >= 0 && playheadProgress <= 1) {
            const playheadX = playheadProgress * width;
            
            ctx.shadowColor = 'rgba(243, 139, 168, 0.8)';
            ctx.shadowBlur = 8;
            ctx.strokeStyle = this.colors.red;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(playheadX, 0);
            ctx.lineTo(playheadX, height);
            ctx.stroke();
            ctx.shadowBlur = 0;
        }
    }

    /**
     * Draw the frequency timeline - shows peak frequencies over time
     * Much more human-readable than a spectrogram
     * @param {Object} analysisData - Frequency analysis data from AudioEngine
     * @param {number} playheadProgress - Optional 0-1 value for playhead position
     */
    drawFrequencyTimeline(analysisData, playheadProgress = null) {
        // Cache analysis data for hover interaction
        this.cachedAnalysis = analysisData;
        
        const ctx = this.frequencyTimelineCtx;
        const baseWidth = 600;
        const zoomedWidth = baseWidth * this.zoom;
        const height = this.frequencyTimelineCanvas.height;
        
        // Resize canvas if needed for zoom
        if (this.frequencyTimelineCanvas.width !== zoomedWidth) {
            this.frequencyTimelineCanvas.width = zoomedWidth;
        }
        
        const width = this.frequencyTimelineCanvas.width;
        
        // Reserve space for axes
        const leftMargin = 55;
        const bottomMargin = 25;
        const topMargin = 10;
        const plotWidth = width - leftMargin - 10;
        const plotHeight = height - bottomMargin - topMargin;
        
        // Clear with gradient background
        const bgGrad = ctx.createLinearGradient(0, 0, 0, height);
        bgGrad.addColorStop(0, this.colors.bg);
        bgGrad.addColorStop(1, this.colors.bgAlt);
        ctx.fillStyle = bgGrad;
        ctx.fillRect(0, 0, width, height);
        
        if (!analysisData || !analysisData.timeline || analysisData.timeline.length === 0) {
            ctx.fillStyle = this.colors.text;
            ctx.font = '500 12px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('Record or upload audio to see frequency timeline', width / 2, height / 2);
            return;
        }
        
        const { timeline, totalDuration } = analysisData;
        
        // Determine frequency range (focus on 100Hz - 5000Hz for alarms)
        const minFreq = 100;
        const maxFreq = 5000;
        const freqRange = maxFreq - minFreq;
        
        // Draw frequency axis (Y)
        ctx.fillStyle = this.colors.text;
        ctx.font = '500 9px Inter, sans-serif';
        ctx.textAlign = 'right';
        
        const freqTicks = [100, 500, 1000, 2000, 3000, 4000, 5000];
        for (const freq of freqTicks) {
            const y = topMargin + plotHeight - ((freq - minFreq) / freqRange) * plotHeight;
            
            // Grid line
            ctx.strokeStyle = this.colors.gridSubtle;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(leftMargin, y);
            ctx.lineTo(width - 10, y);
            ctx.stroke();
            
            // Label
            ctx.fillStyle = this.colors.text;
            const label = freq >= 1000 ? `${(freq / 1000).toFixed(1)}kHz` : `${freq}Hz`;
            ctx.fillText(label, leftMargin - 8, y + 3);
        }
        
        // Draw time axis (X)
        this.drawTimeAxisForTimeline(ctx, leftMargin, plotWidth, height, bottomMargin, totalDuration);
        
        // Draw peak frequencies as points/bars
        const pixelsPerSecond = plotWidth / totalDuration;
        
        // Draw bars for each frame showing peak frequency
        for (const frame of timeline) {
            const x = leftMargin + frame.time * pixelsPerSecond;
            const barWidth = Math.max(frame.duration * pixelsPerSecond, 2);
            
            // Skip if RMS is too low (silence)
            if (frame.rms < 0.02) continue;
            
            // Draw each peak frequency as a bar
            for (let i = 0; i < Math.min(frame.peakFrequencies.length, 3); i++) {
                const freq = frame.peakFrequencies[i];
                const amplitude = frame.peakAmplitudes[i];
                
                if (freq < minFreq || freq > maxFreq) continue;
                
                const y = topMargin + plotHeight - ((freq - minFreq) / freqRange) * plotHeight;
                
                // Size based on amplitude (primary peak is larger)
                const dotSize = i === 0 ? 6 : (i === 1 ? 4 : 3);
                const alpha = Math.min(amplitude * 50, 1);
                
                // Color based on rank
                const baseColor = this.colors.freqColors[i];
                ctx.fillStyle = baseColor;
                ctx.globalAlpha = Math.max(0.3, alpha);
                
                // Draw as horizontal bar
                this.roundRect(ctx, x, y - dotSize / 2, barWidth, dotSize, 2);
                ctx.fill();
            }
        }
        
        ctx.globalAlpha = 1;
        
        // Draw legend
        this.drawFrequencyLegend(ctx, width - 120, topMargin + 5);
        
        // Draw playhead if provided
        if (playheadProgress !== null && playheadProgress >= 0 && playheadProgress <= 1) {
            const playheadX = leftMargin + playheadProgress * plotWidth;
            
            ctx.shadowColor = 'rgba(243, 139, 168, 0.8)';
            ctx.shadowBlur = 12;
            ctx.strokeStyle = this.colors.red;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(playheadX, topMargin);
            ctx.lineTo(playheadX, height - bottomMargin);
            ctx.stroke();
            ctx.shadowBlur = 0;
        }
    }

    /**
     * Get frequency info at a specific canvas position (for hover tooltip)
     * @param {number} canvasX - X position on canvas
     * @param {number} canvasY - Y position on canvas
     * @returns {Object|null} Frequency info or null if no data
     */
    getFrequencyAtPosition(canvasX, canvasY) {
        if (!this.cachedAnalysis) return null;
        
        const { timeline, totalDuration } = this.cachedAnalysis;
        const width = this.frequencyTimelineCanvas.width;
        const height = this.frequencyTimelineCanvas.height;
        
        const leftMargin = 55;
        const bottomMargin = 25;
        const topMargin = 10;
        const plotWidth = width - leftMargin - 10;
        const plotHeight = height - bottomMargin - topMargin;
        
        // Check if within plot area
        if (canvasX < leftMargin || canvasX > width - 10 || 
            canvasY < topMargin || canvasY > height - bottomMargin) {
            return null;
        }
        
        const pixelsPerSecond = plotWidth / totalDuration;
        const time = (canvasX - leftMargin) / pixelsPerSecond;
        
        // Find closest frame
        const frame = timeline.find(f => time >= f.time && time < f.time + f.duration);
        if (!frame) return null;
        
        // Calculate frequency from Y position
        const minFreq = 100;
        const maxFreq = 5000;
        const freqRange = maxFreq - minFreq;
        const relY = (canvasY - topMargin) / plotHeight;
        const frequency = maxFreq - relY * freqRange;
        
        return {
            time: frame.time,
            peakFrequencies: frame.peakFrequencies,
            peakAmplitudes: frame.peakAmplitudes,
            rms: frame.rms,
            cursorFrequency: Math.round(frequency)
        };
    }

    /**
     * Convert canvas X position to time (for audiogram crop selection)
     * @param {number} canvasX - X position on canvas
     * @returns {number} Time in seconds
     */
    canvasXToTime(canvasX) {
        if (!this.cachedAnalysis) return 0;
        const { totalDuration } = this.cachedAnalysis;
        const width = this.audiogramCanvas.width;
        return Math.max(0, Math.min(totalDuration, (canvasX / width) * totalDuration));
    }

    /**
     * Set crop selection region
     * @param {number} startTime - Start time in seconds
     * @param {number} endTime - End time in seconds
     */
    setCropSelection(startTime, endTime) {
        if (startTime > endTime) {
            [startTime, endTime] = [endTime, startTime];
        }
        this.cropSelection = { start: startTime, end: endTime };
    }

    /**
     * Clear crop selection
     */
    clearCropSelection() {
        this.cropSelection = null;
    }

    /**
     * Get current crop selection
     * @returns {Object|null} Crop selection or null
     */
    getCropSelection() {
        return this.cropSelection;
    }

    /**
     * Set zoom level
     * @param {number} level - Zoom level (1.0 = 100%)
     */
    setZoom(level) {
        this.zoom = Math.max(1.0, Math.min(this.maxZoom, level));
    }

    /**
     * Get current zoom level
     * @returns {number} Current zoom level
     */
    getZoom() {
        return this.zoom;
    }

    /**
     * Draw a simple legend for the frequency timeline
     */
    drawFrequencyLegend(ctx, x, y) {
        const labels = ['1st Peak', '2nd Peak', '3rd Peak'];
        
        ctx.font = '500 8px Inter, sans-serif';
        ctx.textAlign = 'left';
        
        for (let i = 0; i < 3; i++) {
            const dotY = y + i * 14;
            
            // Color dot
            ctx.fillStyle = this.colors.freqColors[i];
            ctx.beginPath();
            ctx.arc(x + 4, dotY, 4, 0, Math.PI * 2);
            ctx.fill();
            
            // Label
            ctx.fillStyle = this.colors.text;
            ctx.fillText(labels[i], x + 14, dotY + 3);
        }
    }

    /**
     * Draw time axis for frequency timeline
     */
    drawTimeAxisForTimeline(ctx, leftMargin, plotWidth, height, bottomMargin, duration) {
        const axisY = height - bottomMargin + 2;
        
        // Axis line
        ctx.strokeStyle = this.colors.grid;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(leftMargin, axisY);
        ctx.lineTo(leftMargin + plotWidth, axisY);
        ctx.stroke();
        
        // Calculate nice tick intervals
        const interval = this._getNiceInterval(duration);
        
        ctx.fillStyle = this.colors.text;
        ctx.font = '500 9px Inter, sans-serif';
        ctx.textAlign = 'center';
        
        const pixelsPerSecond = plotWidth / duration;
        
        for (let t = 0; t <= duration; t += interval) {
            const x = leftMargin + t * pixelsPerSecond;
            
            // Tick mark
            ctx.strokeStyle = this.colors.grid;
            ctx.beginPath();
            ctx.moveTo(x, axisY);
            ctx.lineTo(x, axisY + 4);
            ctx.stroke();
            
            // Time label
            const label = t < 1 ? `${(t * 1000).toFixed(0)}ms` : `${t.toFixed(1)}s`;
            ctx.fillText(label, x, height - 4);
        }
    }

    /**
     * Get a nice interval for time ticks
     */
    _getNiceInterval(duration) {
        const targetTicks = 8;
        const rawInterval = duration / targetTicks;
        const niceIntervals = [0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10];
        return niceIntervals.find(i => i >= rawInterval) || rawInterval;
    }

    /**
     * Live update of frequency timeline during playback
     */
    drawLiveFrequency(freqData, bufferLength) {
        // For live display, just draw current frequency distribution
        const ctx = this.frequencyTimelineCtx;
        const width = this.frequencyTimelineCanvas.width;
        const height = this.frequencyTimelineCanvas.height;
        
        // Clear
        const bgGrad = ctx.createLinearGradient(0, 0, 0, height);
        bgGrad.addColorStop(0, this.colors.bg);
        bgGrad.addColorStop(1, this.colors.bgAlt);
        ctx.fillStyle = bgGrad;
        ctx.fillRect(0, 0, width, height);
        
        // Draw "LIVE" indicator
        ctx.fillStyle = this.colors.red;
        ctx.font = '600 10px Inter, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText('● LIVE', 10, 18);
        
        ctx.fillStyle = this.colors.text;
        ctx.font = '500 11px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Frequency analysis will appear after recording', width / 2, height / 2);
    }

    /**
     * Live audiogram during recording
     */
    drawLiveAudiogram(timeData, bufferLength) {
        const ctx = this.audiogramCtx;
        const width = this.audiogramCanvas.width;
        const height = this.audiogramCanvas.height;
        
        // Clear with gradient background
        const bgGrad = ctx.createLinearGradient(0, 0, 0, height);
        bgGrad.addColorStop(0, this.colors.bg);
        bgGrad.addColorStop(1, this.colors.bgAlt);
        ctx.fillStyle = bgGrad;
        ctx.fillRect(0, 0, width, height);
        
        // Draw "LIVE" indicator
        ctx.fillStyle = this.colors.red;
        ctx.font = '600 10px Inter, sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText('● RECORDING', 10, 18);
        
        // Draw live waveform
        ctx.strokeStyle = this.colors.audiogram;
        ctx.lineWidth = 1.5;
        ctx.shadowColor = this.colors.audiogramGlow;
        ctx.shadowBlur = 6;
        ctx.beginPath();
        
        const sliceWidth = width / bufferLength;
        let x = 0;
        
        for (let i = 0; i < bufferLength; i++) {
            const v = timeData[i] / 128.0;
            const y = (v * height) / 2;
            
            if (i === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
            x += sliceWidth;
        }
        
        ctx.stroke();
        ctx.shadowBlur = 0;
    }

    drawEvents(events, duration) {
        const ctx = this.eventsCtx;
        const width = this.eventsCanvas.width;
        const height = this.eventsCanvas.height;
        
        // Reserve space for time axis
        const axisHeight = 18;
        const plotHeight = height - axisHeight;
        
        // Clear with gradient
        const bgGrad = ctx.createLinearGradient(0, 0, 0, height);
        bgGrad.addColorStop(0, this.colors.bg);
        bgGrad.addColorStop(1, this.colors.bgAlt);
        ctx.fillStyle = bgGrad;
        ctx.fillRect(0, 0, width, height);
        
        if (!events || events.length === 0 || duration === 0) {
            ctx.fillStyle = this.colors.text;
            ctx.font = '500 12px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('No events detected yet', width / 2, plotHeight / 2 + 4);
            return;
        }
        
        const pixelsPerSecond = width / duration;
        
        // Draw events
        for (const event of events) {
            const x = event.timestamp * pixelsPerSecond;
            const w = event.duration * pixelsPerSecond;
            
            if (event.type === 'tone') {
                // Draw tone event with rounded corners and glow
                ctx.shadowColor = 'rgba(166, 227, 161, 0.4)';
                ctx.shadowBlur = 8;
                ctx.fillStyle = this.colors.eventTone;
                this.roundRect(ctx, x, 6, Math.max(w - 2, 4), plotHeight - 12, 4);
                ctx.fill();
                ctx.shadowBlur = 0;
                
                // Frequency label
                ctx.fillStyle = this.colors.bg;
                ctx.font = '600 9px Inter, sans-serif';
                ctx.textAlign = 'center';
                if (w > 25) {
                    ctx.fillText(`${Math.round(event.frequency)}Hz`, x + w/2, plotHeight/2 + 2);
                }
            } else {
                ctx.fillStyle = this.colors.eventSilence;
                this.roundRect(ctx, x, 14, Math.max(w - 2, 4), plotHeight - 28, 4);
                ctx.fill();
            }
        }
        
        // Draw time axis
        this.drawTimeAxis(ctx, width, height, plotHeight, duration);
    }

    /**
     * Draw a time axis at the bottom of the canvas
     */
    drawTimeAxis(ctx, width, height, plotHeight, duration) {
        const axisY = plotHeight + 2;
        
        // Axis line
        ctx.strokeStyle = this.colors.grid;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, axisY);
        ctx.lineTo(width, axisY);
        ctx.stroke();
        
        // Calculate nice tick intervals
        const interval = this._getNiceInterval(duration);
        
        ctx.fillStyle = this.colors.text;
        ctx.font = '500 9px Inter, sans-serif';
        ctx.textAlign = 'center';
        
        const pixelsPerSecond = width / duration;
        
        for (let t = 0; t <= duration; t += interval) {
            const x = t * pixelsPerSecond;
            
            // Tick mark
            ctx.strokeStyle = this.colors.grid;
            ctx.beginPath();
            ctx.moveTo(x, axisY);
            ctx.lineTo(x, axisY + 4);
            ctx.stroke();
            
            // Time label
            const label = t < 1 ? `${(t * 1000).toFixed(0)}ms` : `${t.toFixed(1)}s`;
            ctx.fillText(label, x, height - 2);
        }
    }

    /**
     * Draw a visual representation of segments from the ruleset.
     * Enhanced with event timeline overlay for sync visualization.
     * @param {Array} segments - Array of segment objects
     * @param {number} cycles - Number of times to repeat the pattern
     * @param {number} playheadProgress - Optional 0-1 value for playhead position
     * @param {Array} eventTimeline - Optional array of generated events for sync
     */
    drawSegmentPreview(segments, cycles = 1, playheadProgress = null, eventTimeline = null) {
        const ctx = this.eventsCtx;
        const width = this.eventsCanvas.width;
        const height = this.eventsCanvas.height;
        
        // Reserve space for time axis
        const axisHeight = 18;
        const plotHeight = height - axisHeight;
        
        // Clear with gradient
        const bgGrad = ctx.createLinearGradient(0, 0, 0, height);
        bgGrad.addColorStop(0, this.colors.bg);
        bgGrad.addColorStop(1, this.colors.bgAlt);
        ctx.fillStyle = bgGrad;
        ctx.fillRect(0, 0, width, height);
        
        if (!segments || segments.length === 0) {
            ctx.fillStyle = this.colors.text;
            ctx.font = '500 12px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('Add segments to preview pattern', width / 2, plotHeight / 2 + 4);
            return;
        }
        
        // Calculate total duration
        let totalDuration = 0;
        for (let c = 0; c < cycles; c++) {
            for (const seg of segments) {
                totalDuration += (seg.durationMin + seg.durationMax) / 2;
            }
        }
        
        const pixelsPerSecond = width / totalDuration;
        let x = 0;
        let toneIndex = 0;
        
        // Define Catppuccin tone colors for variety (only for tones)
        const toneColors = [
            { fill: this.colors.eventTone, glow: 'rgba(166, 227, 161, 0.4)' },    // green
            { fill: this.colors.accentAlt, glow: 'rgba(116, 199, 236, 0.4)' },    // sapphire
            { fill: this.colors.peach, glow: 'rgba(250, 179, 135, 0.4)' },        // peach
            { fill: this.colors.pink, glow: 'rgba(245, 194, 231, 0.4)' }          // pink
        ];
        
        for (let c = 0; c < cycles; c++) {
            for (const seg of segments) {
                const duration = (seg.durationMin + seg.durationMax) / 2;
                const w = duration * pixelsPerSecond;
                
                if (seg.type === 'tone') {
                    const avgFreq = (seg.freqMin + seg.freqMax) / 2;
                    const colorIndex = toneIndex % toneColors.length;
                    const color = toneColors[colorIndex];
                    toneIndex++;
                    
                    // Draw with glow
                    ctx.shadowColor = color.glow;
                    ctx.shadowBlur = 10;
                    ctx.fillStyle = color.fill;
                    this.roundRect(ctx, x + 1, 6, w - 4, plotHeight - 12, 6);
                    ctx.fill();
                    ctx.shadowBlur = 0;
                    
                    // Frequency label
                    ctx.fillStyle = this.colors.bg;
                    ctx.font = '600 9px Inter, sans-serif';
                    ctx.textAlign = 'center';
                    if (w > 35) {
                        ctx.fillText(`${Math.round(avgFreq)}Hz`, x + w/2, plotHeight/2);
                    }
                } else {
                    // Silence - distinct muted style
                    ctx.fillStyle = this.colors.eventSilence;
                    this.roundRect(ctx, x + 1, 16, w - 4, plotHeight - 32, 4);
                    ctx.fill();
                    
                    // Optional: Draw pause icon in center for larger silences
                    if (w > 20) {
                        ctx.fillStyle = this.colors.text;
                        ctx.font = '500 10px Inter, sans-serif';
                        ctx.textAlign = 'center';
                        ctx.fillText('⏸', x + w/2, plotHeight/2 + 2);
                    }
                }
                
                x += w;
            }
        }
        
        // Cycle markers with subtle styling
        ctx.strokeStyle = 'rgba(205, 214, 244, 0.2)';
        ctx.setLineDash([6, 6]);
        ctx.lineWidth = 1;
        x = 0;
        for (let c = 0; c < cycles; c++) {
            for (const seg of segments) {
                x += ((seg.durationMin + seg.durationMax) / 2) * pixelsPerSecond;
            }
            if (c < cycles - 1) {
                ctx.beginPath();
                ctx.moveTo(x, 0);
                ctx.lineTo(x, plotHeight);
                ctx.stroke();
            }
        }
        ctx.setLineDash([]);
        
        // Draw time axis
        this.drawTimeAxis(ctx, width, height, plotHeight, totalDuration);
        
        // Draw playhead if progress is provided
        if (playheadProgress !== null && playheadProgress >= 0 && playheadProgress <= 1) {
            const playheadX = playheadProgress * width;
            
            // Glowing playhead line
            ctx.shadowColor = 'rgba(243, 139, 168, 0.8)';
            ctx.shadowBlur = 12;
            ctx.strokeStyle = this.colors.red;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(playheadX, 0);
            ctx.lineTo(playheadX, plotHeight);
            ctx.stroke();
            ctx.shadowBlur = 0;
            
            // Playhead triangle indicator at top
            ctx.fillStyle = this.colors.red;
            ctx.beginPath();
            ctx.moveTo(playheadX - 5, 0);
            ctx.lineTo(playheadX + 5, 0);
            ctx.lineTo(playheadX, 8);
            ctx.closePath();
            ctx.fill();
        }
    }
    
    /**
     * Helper to draw rounded rectangles
     */
    roundRect(ctx, x, y, width, height, radius) {
        ctx.beginPath();
        ctx.moveTo(x + radius, y);
        ctx.lineTo(x + width - radius, y);
        ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
        ctx.lineTo(x + width, y + height - radius);
        ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
        ctx.lineTo(x + radius, y + height);
        ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
        ctx.lineTo(x, y + radius);
        ctx.quadraticCurveTo(x, y, x + radius, y);
        ctx.closePath();
    }

    clear() {
        this.detectedEvents = [];
        this.cropSelection = null;
        this.cachedAnalysis = null;
        this.zoom = 1.0;
        
        // Reset canvas width
        this.frequencyTimelineCanvas.width = 600;
        
        [this.audiogramCanvas, this.frequencyTimelineCanvas, this.eventsCanvas].forEach(canvas => {
            const ctx = canvas.getContext('2d');
            const bgGrad = ctx.createLinearGradient(0, 0, 0, canvas.height);
            bgGrad.addColorStop(0, this.colors.bg);
            bgGrad.addColorStop(1, this.colors.bgAlt);
            ctx.fillStyle = bgGrad;
            ctx.fillRect(0, 0, canvas.width, canvas.height);
        });
    }
}

window.Visualizer = Visualizer;
