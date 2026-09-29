let currentTool = 'healthy';
let lastClickedTooth = null;

function setTool(el) {
    document.querySelectorAll('.tool').forEach(t => t.classList.remove('active'));
    el.classList.add('active');
    currentTool = el.getAttribute('data-tool');
}

function createToothSVG(id) {
    return `
    <div class="tooth-unit" id="tooth-${id}">
        <span class="tooth-label">${id}</span>
        <svg class="tooth-svg" viewBox="0 0 100 100" onclick="handleToothAction('${id}')">
            <path class="segment" d="M50,50 L12,12 A54,54 0 0,1 88,12 Z" onclick="paintSegment(event)" /> 
            <path class="segment" d="M50,50 L88,12 A54,54 0 0,1 88,88 Z" onclick="paintSegment(event)" /> 
            <path class="segment" d="M50,50 L88,88 A54,54 0 0,1 12,88 Z" onclick="paintSegment(event)" /> 
            <path class="segment" d="M50,50 L12,88 A54,54 0 0,1 12,12 Z" onclick="paintSegment(event)" /> 
            <circle class="segment" cx="50" cy="50" r="23" onclick="paintSegment(event)" />
            
            <line class="mark-line" x1="50" y1="5" x2="50" y2="95" stroke-width="8" style="display:none; pointer-events:none;" />
            
            <g class="mark-x" style="display:none; pointer-events:none; stroke:#ff4d4d; stroke-width:8;">
                <line x1="20" y1="20" x2="80" y2="80" />
                <line x1="80" y1="20" x2="20" y2="80" />
            </g>
        </svg>
    </div>`;
}

function paintSegment(e) {
    if (currentTool === 'caries' || currentTool === 'filling') {
        e.stopPropagation(); // Stops the modal from popping up
        e.target.style.fill = (currentTool === 'caries') ? '#ff4d4d' : '#156699';
    }
}

function handleToothAction(id) {
    const tooth = document.getElementById(`tooth-${id}`);
    const markX = tooth.querySelector('.mark-x');
    const markLine = tooth.querySelector('.mark-line');

    if (currentTool === 'healthy') {
        tooth.querySelectorAll('.segment').forEach(s => s.style.fill = '#ffffff');
        markX.style.display = 'none';
        markLine.style.display = 'none';
    } 
    else if (currentTool === 'extraction') {
        markX.style.display = (markX.style.display === 'block') ? 'none' : 'block';
    }
    else if (currentTool === 'crown' || currentTool === 'rootcanal') {
        lastClickedTooth = id;
        document.getElementById('tool-modal').style.display = 'flex';
    }
}

function applyModalChoice(color) {
    const tooth = document.getElementById(`tooth-${lastClickedTooth}`);
    if (currentTool === 'crown') {
        tooth.querySelectorAll('.segment').forEach(s => s.style.fill = color);
    } else if (currentTool === 'rootcanal') {
        const line = tooth.querySelector('.mark-line');
        line.setAttribute('stroke', color);
        line.style.display = 'block';
    }
    closeModal();
}

function closeModal() { document.getElementById('tool-modal').style.display = 'none'; }

function initUnifiedGrid(id, cols) {
    const grid = document.getElementById(id);
    if (!grid) return;
    grid.innerHTML = ''; // Clear existing
    for (let i = 0; i < cols * 2; i++) {
        const box = document.createElement('div');
        box.className = 'grid-box';
        box.onclick = function() {
            if (currentTool === 'check') this.innerHTML = (this.innerHTML === '✔️') ? '' : '✔️';
        };
        grid.appendChild(box);
    }
}

window.onload = () => {
    initUnifiedGrid('grid-upper', 10);
    initUnifiedGrid('grid-perm-upper', 16);
    initUnifiedGrid('grid-perm-lower', 16);
    initUnifiedGrid('grid-lower', 10);

    const render = (rowId, nums) => {
        const row = document.getElementById(rowId);
        if(row) nums.forEach(n => row.innerHTML += createToothSVG(n));
    };

    render('teeth-temp-top', [55, 54, 53, 52, 51, 61, 62, 63, 64, 65]);
    render('teeth-perm-top', [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28]);
    render('teeth-perm-bottom', [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38]);
    render('teeth-temp-bottom', [85, 84, 83, 82, 81, 71, 72, 73, 74, 75]);
};