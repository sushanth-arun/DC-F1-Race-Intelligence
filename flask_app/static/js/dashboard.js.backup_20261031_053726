const uploadForm = document.getElementById("uploadForm");
const fileInput = document.getElementById("datasetFile");
const fileLabel = document.getElementById("fileLabel");
const uploadButton = document.getElementById("uploadButton");
const uploadMessage = document.getElementById("uploadMessage");

let currentJobId = null;
let pollingTimer = null;
const charts = {};

const palette = [
    "#e10600", "#42a5f5", "#42d6a0", "#f5b942",
    "#b58cff", "#ff83b7", "#55d6d2", "#f58c42",
    "#a5d66f", "#929baa"
];

const tyreColours = {
    SOFT: "#e10600",
    MEDIUM: "#ffd12e",
    HARD: "#f5f5f5",
    INTERMEDIATE: "#39b96b",
    WET: "#368bd6"
};

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value ?? "—";
}

async function checkHealth() {
    try {
        const response = await fetch("/api/health");
        const data = await response.json();
        const connection = document.querySelector(".connection");

        if (connection) {
            connection.innerHTML =
                `<i></i> ${data.status === "ONLINE" ? "HADOOP CONNECTED" : "HADOOP OFFLINE"}`;
        }
    } catch (error) {
        const connection = document.querySelector(".connection");
        if (connection) connection.textContent = "CONNECTION ERROR";
    }
}

function clearDashboard() {
    Object.values(charts).forEach(chart => chart.destroy());

    Object.keys(charts).forEach(key => delete charts[key]);

    [
        "totalRaces", "totalDrivers", "totalConstructors",
        "totalLaps", "activeSeason"
    ].forEach(id => setText(id, "—"));

    [
        "driverChart", "constructorChart", "raceChart", "gainChart",
        "pitChart", "lapChart", "lapTrendChart", "tyreChart",
        "consistencyChart", "fanChart"
    ].forEach(id => {
        const canvas = document.getElementById(id);
        if (canvas) {
            const parent = canvas.parentElement;
            const message = parent.querySelector(".empty-chart-message");
            if (message) message.remove();
        }
    });

    [
        "pitTable", "qualifyingTable", "constructorTable"
    ].forEach(id => {
        const element = document.getElementById(id);
        if (element) element.innerHTML = "";
    });
}


function setDashboardVisible(visible) {
    document.querySelectorAll("main.container > section.section").forEach(section => {
        section.style.display = visible ? "" : "none";
    });
}

fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    fileLabel.textContent = file ? file.name : "Choose race ZIP file";
    if (file) setDashboardVisible(false);

    if (pollingTimer) {
        clearInterval(pollingTimer);
        pollingTimer = null;
    }

    currentJobId = null;
    clearDashboard();
    setDashboardVisible(false);

    uploadMessage.textContent = file
        ? "New race selected. Ready for validation."
        : "";

    setText("jobStatus", "READY");
    setText("jobMessage", "Waiting for dataset upload");
    setText("jobProgress", "0%");

    const bar = document.getElementById("progressBar");
    if (bar) bar.style.width = "0%";

    uploadButton.disabled = false;
    uploadButton.textContent = "ANALYSE RACE ↗";
});

uploadForm.addEventListener("submit", async event => {
    event.preventDefault();

    const file = fileInput.files[0];

    if (!file || !file.name.toLowerCase().endsWith(".zip")) {
        uploadMessage.textContent = "Please select a ZIP archive.";
        return;
    }

    if (file.size > 100 * 1024 * 1024) {
        uploadMessage.textContent = "File exceeds the 100 MB upload limit.";
        return;
    }

    if (pollingTimer) {
        clearInterval(pollingTimer);
        pollingTimer = null;
    }

    clearDashboard();

    const formData = new FormData();
    formData.append("file", file);

    uploadButton.disabled = true;
    uploadButton.textContent = "UPLOADING...";
    uploadMessage.textContent = "Uploading race dataset...";

    setText("jobStatus", "QUEUED");
    setText("jobMessage", "Waiting for validation...");
    setText("jobProgress", "0%");
    document.getElementById("progressBar").style.width = "0%";

    try {
        const response = await fetch("/api/upload", {
            method: "POST",
            body: formData
        });

        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Upload failed");

        currentJobId = data.job_id;
        setText("jobId", "Job ID: " + currentJobId);

        await checkJobStatus();

        if (pollingTimer) clearInterval(pollingTimer);
        pollingTimer = setInterval(checkJobStatus, 2000);

    } catch (error) {
        uploadMessage.textContent = error.message;
        uploadButton.disabled = false;
        uploadButton.textContent = "RETRY UPLOAD →";
    }
});

async function checkJobStatus() {
    if (!currentJobId) return;

    try {
        const response = await fetch(`/api/jobs/${currentJobId}`);
        const job = await response.json();

        if (!response.ok) throw new Error(job.error || "Job lookup failed");

        setText("jobStatus", job.status);
        setText("jobMessage", job.message || "Processing...");

        let progress = 15;
        if (job.status === "VALIDATING") progress = 45;
        if (job.status === "COMPLETED" || job.status === "FAILED") progress = 100;

        document.getElementById("progressBar").style.width = progress + "%";
        setText("jobProgress", progress + "%");

        if (job.status === "COMPLETED") {
            setDashboardVisible(true);
            renderAnalytics(job.result.analytics);

            uploadMessage.textContent = "Race analysed successfully.";
            uploadButton.disabled = false;
            uploadButton.textContent = "UPLOAD ANOTHER RACE →";

            clearInterval(pollingTimer);
            pollingTimer = null;
        }

        if (job.status === "FAILED") {
            uploadMessage.textContent = "Processing failed: " + job.message;
            uploadButton.disabled = false;
            uploadButton.textContent = "RETRY UPLOAD →";

            clearInterval(pollingTimer);
            pollingTimer = null;
        }

    } catch (error) {
        setText("jobMessage", error.message);

        if (pollingTimer) clearInterval(pollingTimer);
        pollingTimer = null;

        uploadButton.disabled = false;
        uploadButton.textContent = "RETRY UPLOAD →";
    }
}

function drawChart(id, type, labels, datasets, extraOptions = {}) {
    const canvas = document.getElementById(id);
    if (!canvas) return;

    if (charts[id]) charts[id].destroy();

    const options = {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 650 },
        interaction: {
            intersect: false,
            mode: "index"
        },
        plugins: {
            legend: {
                display: datasets.length > 1 || type === "doughnut",
                position: "bottom",
                labels: {
                    color: "#aab2c0",
                    usePointStyle: true,
                    padding: 18
                }
            },
            tooltip: {
                backgroundColor: "#202631",
                titleColor: "#ffffff",
                bodyColor: "#dce1e9",
                borderColor: "#3a4352",
                borderWidth: 1
            }
        },
        scales: type === "doughnut" ? {} : {
            x: {
                ticks: { color: "#929baa" },
                grid: { display: false }
            },
            y: {
                beginAtZero: true,
                ticks: { color: "#929baa" },
                grid: { color: "rgba(255,255,255,.07)" }
            }
        },
        ...extraOptions
    };

    charts[id] = new Chart(canvas, {
        type,
        data: { labels, datasets },
        options
    });
}

function renderTable(id, rows, columns, emptyMessage) {
    const body = document.getElementById(id);
    if (!body) return;

    if (!rows || !rows.length) {
        body.innerHTML =
            `<tr><td colspan="${columns.length}">${emptyMessage}</td></tr>`;
        return;
    }

    body.innerHTML = rows.map(row =>
        "<tr>" + columns.map(column =>
            `<td>${escapeHTML(column(row))}</td>`
        ).join("") + "</tr>"
    ).join("");
}

function escapeHTML(value) {
    return String(value ?? "—").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    })[char]);
}

function renderAnalytics(data) {
    renderTopPerformance(data);

    if (!data) return;

    const overview = data.overview || {};

    setText("totalRaces", "1");
    setText("totalDrivers", overview.drivers);
    setText("totalConstructors", overview.constructors);
    setText("totalLaps", overview.laps);

    setText(
        "activeSeason",
        `SEASON ${data.race.season} · ROUND ${data.race.round} · ${data.race.race_id}`
    );

    setText("winner", data.winner);
    setText("winningTime", overview.winning_time);

    const bar = (id, dataset, label, colour) => {
        if (!dataset) return;

        drawChart(id, "bar", dataset.labels, [{
            label,
            data: dataset.values,
            backgroundColor: colour || "#42a5f5",
            borderRadius: 5,
            maxBarThickness: 32
        }]);
    };

    bar("driverChart", data.driver_points, "Points", "#e10600");
    bar("constructorChart", data.constructor_points, "Points", "#42a5f5");
    bar("raceChart", data.finishing_positions, "Finish position", "#42d6a0");
    bar("gainChart", data.position_gains, "Places gained", "#b58cff");

    // PIT STOP ANALYSIS
    if (data.pit_stops) {
        drawChart("pitChart", "bar", data.pit_stops.labels, [{
            label: "Average stationary pit time (seconds)",
            data: data.pit_stops.values,
            backgroundColor: "#42d6a0",
            borderRadius: 5,
            maxBarThickness: 35
        }], {
            indexAxis: "y",
            scales: {
                x: {
                    beginAtZero: true,
                    title: { display: true, text: "Seconds", color: "#929baa" },
                    ticks: { color: "#929baa" },
                    grid: { color: "rgba(255,255,255,.07)" }
                },
                y: {
                    ticks: { color: "#929baa" },
                    grid: { display: false }
                }
            }
        });
    }

    renderTable("pitTable", data.pit_stop_leaderboard, [
        row => row.driver,
        row => row.team,
        row => row.lap,
        row => Number(row.stationary).toFixed(3) + " s"
    ], "No pit-stop data");

    // AVERAGE LAP TIME
    bar("lapChart", data.lap_times, "Average lap time (seconds)", "#42a5f5");

    // LAP-BY-LAP PACE: relative to each driver's own average, in milliseconds.
    if (data.lap_trend) {
        const datasets = data.lap_trend.datasets.map((series, index) => ({
            label: series.label,
            data: series.values.map(value =>
                value === null || value === undefined ? null : value
            ),
            borderColor: palette[index % palette.length],
            backgroundColor: palette[index % palette.length],
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 5,
            tension: 0.22,
            spanGaps: false
        }));

        drawChart("lapTrendChart", "line", data.lap_trend.labels, datasets, {
            scales: {
                x: {
                    title: { display: true, text: "Race lap", color: "#929baa" },
                    ticks: { color: "#929baa" },
                    grid: { display: false }
                },
                y: {
                    beginAtZero: false,
                    title: {
                        display: true,
                        text: "Lap-time difference (milliseconds)",
                        color: "#929baa"
                    },
                    ticks: {
                        color: "#929baa",
                        callback: value => (value > 0 ? "+" : "") + value + " ms"
                    },
                    grid: { color: "rgba(255,255,255,.07)" }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: "bottom",
                    labels: { color: "#aab2c0", usePointStyle: true }
                },
                tooltip: {
                    callbacks: {
                        label: context =>
                            `${context.dataset.label}: ${context.parsed.y > 0 ? "+" : ""}${context.parsed.y} ms`
                    }
                }
            }
        });
    }

    // TYRE COMPOUND USAGE
    if (data.tyre_usage) {
        const colours = data.tyre_usage.labels.map(compound =>
            tyreColours[String(compound).toUpperCase()] || "#929baa"
        );

        drawChart("tyreChart", "doughnut", data.tyre_usage.labels, [{
            label: "Recorded laps by compound",
            data: data.tyre_usage.values,
            backgroundColor: colours,
            borderColor: "#171a22",
            borderWidth: 3,
            hoverOffset: 9
        }], {
            cutout: "65%"
        });
    }

    if (data.consistency) {
        drawChart(
            "consistencyChart",
            "bar",
            data.consistency.map(row => row.driver),
            [{
                label: "Lap-time standard deviation (seconds)",
                data: data.consistency.map(row => row.deviation),
                backgroundColor: "#f5b942",
                borderRadius: 5
            }]
        );
    }

    renderTable("qualifyingTable", data.qualifying, [
        row => "P" + row.qualifying_position,
        row => row.driver,
        row => row.team,
        row => row.qualifying_time,
        row => row.race_position ? "P" + row.race_position : "—",
        row => row.gain === null ? "—" : (row.gain > 0 ? "+" : "") + row.gain
    ], "No qualifying data");

    renderTable("constructorTable", data.constructor_standings, [
        row => row.position,
        row => row.team,
        row => row.race_points,
        row => row.cumulative_points,
        row => row.wins,
        row => row.podiums
    ], "No constructor standings data");

    if (data.driver_of_the_day) {
        drawChart("fanChart", "bar",
            data.driver_of_the_day.map(row => row.driver), [{
                label: "Fan votes",
                data: data.driver_of_the_day.map(row => row.votes),
                backgroundColor: "#f472b6",
                borderRadius: 5
            }]);
    }

    setText("sectorMessage", "");
}

checkHealth();
setInterval(checkHealth, 15000);

// TOP PERFORMANCE CARDS
function renderTopPerformance(data) {
    const set = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value ?? "Data unavailable";
    };

    const valid = value =>
        value !== null && value !== undefined && value !== "" && value !== "Unavailable";

    const winner = data.winner;
    set("winnerName", valid(winner) ? winner : "Data unavailable");
    set("winnerTeam", data.winner_team || " ");

    const fan = data.fan_favourite || {};
    set("fanName", fan.driver || "Data unavailable");
    set("fanDetail", fan.votes != null ? `${fan.votes.toLocaleString()} votes · Driver of the Day` : "Driver of the Day");

    const fastest = data.fastest_lap || {};
    set("fastestName", fastest.driver || "Data unavailable");
    set("fastestDetail", fastest.time || (fastest.seconds ? `${fastest.seconds} seconds · Lap ${fastest.lap}` : "Fastest recorded lap"));

    const pit = data.best_pit_stop || {};
    set("pitName", pit.driver || "Data unavailable");
    set("pitDetail", pit.stationary > 0 ? `${pit.stationary.toFixed(3)} seconds · Lap ${pit.lap}` : "Stationary stop duration unavailable");

    const pole = data.pole || {};
    set("poleName", pole.driver || "Data unavailable");
    set("poleDetail", pole.time || "Qualifying performance");

    const gain = data.biggest_gain || {};
    set("gainName", gain.driver || "Data unavailable");
    set("gainDetail", gain.gain != null ? `Gained ${gain.gain} positions · Grid ${gain.grid} → Finish ${gain.position}` : "Position gain unavailable");
}




/* ===== F1 DASHBOARD TABS ===== */
(function () {
    function setupRaceTabs() {
        const main = document.querySelector("main");
        if (!main || document.querySelector(".race-tabs")) return;

        const sections = Array.from(main.querySelectorAll("section.section"));
        if (!sections.length) return;

        function category(section) {
            const heading = section.querySelector("h2, h3");
            const title = heading ? heading.textContent.toLowerCase() : "";

            if (/overview|top performance|standout|big picture/.test(title))
                return "overview";

            if (/lap|pace|consistency|fastest lap/.test(title))
                return "pace";

            if (/pit|tyre|tire|strategy/.test(title))
                return "strategy";

            if (/constructor|team/.test(title))
                return "teams";

            if (/driver|qualifying|position|result|fan|vote/.test(title))
                return "drivers";

            return "overview";
        }

        sections.forEach(section => {
            section.dataset.raceTab = category(section);
        });

        const tabs = [
            ["overview", "OVERVIEW"],
            ["pace", "RACE PACE"],
            ["drivers", "DRIVERS"],
            ["strategy", "STRATEGY"],
            ["teams", "TEAMS"]
        ];

        const nav = document.createElement("nav");
        nav.className = "race-tabs";

        tabs.forEach(([id, label], index) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "race-tab" + (index === 0 ? " active" : "");
            button.textContent = label;

            button.addEventListener("click", () => {
                nav.querySelectorAll(".race-tab").forEach(b =>
                    b.classList.toggle("active", b === button)
                );

                sections.forEach(section => {
                    section.hidden = section.dataset.raceTab !== id;
                });

                sections.filter(s => !s.hidden).forEach(s => {
                    s.classList.remove("dashboard-tab-content");
                    void s.offsetWidth;
                    s.classList.add("dashboard-tab-content");
                });
            });

            nav.appendChild(button);
        });

        main.insertBefore(nav, sections[0]);

        sections.forEach(section => {
            section.hidden = section.dataset.raceTab !== "overview";
        });
    }

    function improveCharts() {
        if (!window.Chart) return;

        Chart.defaults.font.family = "'Inter', 'Segoe UI', sans-serif";
        Chart.defaults.font.size = 11;
        Chart.defaults.color = "#aebbd0";
        Chart.defaults.borderColor = "rgba(160,177,200,0.12)";
        Chart.defaults.elements.line.tension = 0.3;
        Chart.defaults.elements.line.borderWidth = 2.5;
        Chart.defaults.elements.point.radius = 0;
        Chart.defaults.elements.point.hoverRadius = 5;
        Chart.defaults.elements.bar.borderRadius = 5;
        Chart.defaults.plugins.legend.labels.usePointStyle = true;
        Chart.defaults.plugins.tooltip.backgroundColor = "#10151e";
        Chart.defaults.plugins.tooltip.borderColor = "#3a4658";
        Chart.defaults.plugins.tooltip.borderWidth = 1;
        Chart.defaults.plugins.tooltip.padding = 11;
    }

    function initialise() {
        setupRaceTabs();
        improveCharts();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initialise);
    } else {
        initialise();
    }
})();
