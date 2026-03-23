let currentTool = 'healthy';

function setTool(element, tool) {
    document.querySelectorAll('.tool').forEach(t => t.classList.remove('active'));
    element.classList.add('active');
    currentTool = tool;
}

function generateTeeth(containerId, numbers) {
    const container = document.getElementById(containerId);
    numbers.forEach(num => {
        container.innerHTML += `
            <div class="tooth-unit">
                <span class="tooth-num">${num}</span>
                <div class="tooth-circle">
                    <div class="seg top" onclick="paint(this)"></div>
                    <div class="seg left" onclick="paint(this)"></div>
                    <div class="seg right" onclick="paint(this)"></div>
                    <div class="seg bottom" onclick="paint(this)"></div>
                    <div class="seg center" onclick="paint(this)"></div>
                    <div class="xtraction-mark">❌</div>
                    <div class="crown-line"></div>
                </div>
            </div>`;
    });
}

function generateBoxes(containerId, count) {
    const container = document.getElementById(containerId);
    for (let i = 0; i < count; i++) {
        container.innerHTML += `<div class="stat-box" onclick="markBox(this)"></div>`;
    }
}

function paint(el) {
    const parent = el.parentElement;
    if (currentTool === 'caries') {
        el.className = 'seg ' + el.classList[1] + ' caries';
    } else if (currentTool === 'filling') {
        el.className = 'seg ' + el.classList[1] + ' filling';
    } else if (currentTool === 'healthy') {
        el.className = 'seg ' + el.classList[1];
        parent.querySelector('.xtraction-mark').style.display = 'none';
        parent.querySelector('.crown-line').style.display = 'none';
    } else if (currentTool === 'extraction') {
        parent.querySelector('.xtraction-mark').style.display = 'block';
    } else if (currentTool === 'crown') {
        parent.querySelector('.crown-line').style.display = 'block';
    } else if (currentTool === 'rootcanal') {
        // Root canal: paints center and adds a red vertical line
        parent.querySelector('.seg.center').classList.add('filling');
        parent.querySelector('.crown-line').style.display = 'block';
        parent.querySelector('.crown-line').style.backgroundColor = 'red';
    }
}

function markBox(el) {
    if (currentTool === 'check') el.innerText = '✔️';
    if (currentTool === 'healthy') el.innerText = '';
}

// Initialize based on image numbering
generateBoxes('status-top-1', 10);
generateBoxes('status-top-2', 10);
generateTeeth('temp-teeth-top', [55, 54, 53, 52, 51, 61, 62, 63, 64, 65]);

generateBoxes('status-mid-1', 16);
generateBoxes('status-mid-2', 16);
generateTeeth('perm-teeth-top', [18, 17, 16, 15, 14, 13, 12, 11, 21, 22, 23, 24, 25, 26, 27, 28]);
generateTeeth('perm-teeth-bottom', [48, 47, 46, 45, 44, 43, 42, 41, 31, 32, 33, 34, 35, 36, 37, 38]);
generateBoxes('status-mid-3', 16);
generateBoxes('status-mid-4', 16);

generateTeeth('temp-teeth-bottom', [85, 84, 83, 82, 81, 71, 72, 73, 74, 75]);
generateBoxes('status-bottom-1', 10);
generateBoxes('status-bottom-2', 10);