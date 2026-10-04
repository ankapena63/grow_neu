let selectedItem = null;
const currentPath = document.body.dataset.currentPath;
const urlParams = new URLSearchParams(window.location.search);
const initialSelected = urlParams.get("selected");

if (initialSelected) {
    selectedItem = {
        name: initialSelected,
        type: urlParams.get("type") || "file"
    };
}

const contextMenu = document.getElementById("context-menu");

function hideContextMenu() {
    contextMenu?.classList.remove("context-menu-visible");
}

function showContextMenu(event, item) {
    if (!contextMenu) {
        return;
    }

    selectedItem = item;
    document.querySelectorAll(".item.file").forEach((file) => {
        file.classList.toggle("selected", file === event.currentTarget);
    });

    contextMenu.classList.add("context-menu-visible");
    const margin = 10;
    const left = Math.min(
        event.clientX,
        window.innerWidth - contextMenu.offsetWidth - margin
    );
    const top = Math.min(
        event.clientY,
        window.innerHeight - contextMenu.offsetHeight - margin
    );
    contextMenu.style.left = `${Math.max(margin, left)}px`;
    contextMenu.style.top = `${Math.max(margin, top)}px`;
}

function sendPost(url, data) {
    const form = document.createElement("form");
    form.method = "POST";
    form.action = url;

    Object.entries(data).forEach(([key, value]) => {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = key;
        input.value = value;
        form.append(input);
    });

    document.body.append(form);
    form.submit();
}

function openSelectedFile() {
    if (!selectedItem) {
        return;
    }

    hideContextMenu();
    window.location.href =
        `/explorer?path=${encodeURIComponent(currentPath)}` +
        `&file=${encodeURIComponent(selectedItem.name)}`;
}

function downloadSelectedFile() {
    if (!selectedItem) {
        return;
    }

    hideContextMenu();
    window.location.href =
        `/explorer/download?path=${encodeURIComponent(currentPath)}` +
        `&name=${encodeURIComponent(selectedItem.name)}`;
}

function renameSelectedFile() {
    if (!selectedItem) {
        return;
    }

    hideContextMenu();
    const newName = window.prompt("Neuer Name:", selectedItem.name);
    if (!newName || newName === selectedItem.name) {
        return;
    }

    sendPost("/explorer/rename", {
        path: currentPath,
        old_name: selectedItem.name,
        new_name: newName
    });
}

function deleteSelectedFile() {
    if (!selectedItem) {
        return;
    }

    hideContextMenu();
    if (!window.confirm(`Wirklich löschen: ${selectedItem.name}`)) {
        return;
    }

    sendPost("/explorer/delete", {
        path: currentPath,
        name: selectedItem.name
    });
}

document.querySelectorAll(".item.file").forEach((file) => {
    if (selectedItem?.name === file.dataset.name) {
        file.classList.add("selected");
    }

    file.addEventListener("click", (event) => {
        event.preventDefault();
        const url = new URL(window.location.href);
        url.searchParams.set("selected", file.dataset.name);
        url.searchParams.set("type", file.dataset.type || "file");
        window.location.href = url.toString();
    });

    file.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        event.stopPropagation();
        showContextMenu(event, {
            name: file.dataset.name,
            type: file.dataset.type || "file"
        });
    });
});

document.getElementById("upload-file")?.addEventListener("change", (event) => {
    const selectedFileName = document.getElementById("selected-file-name");
    const file = event.currentTarget.files?.[0];
    if (!selectedFileName) {
        return;
    }

    selectedFileName.textContent = file
        ? `📄 ${file.name}`
        : "❌ Keine Datei ausgewählt";
    selectedFileName.classList.toggle("has-file", Boolean(file));
});

document.querySelectorAll(".toggle-btn").forEach((button) => {
    button.addEventListener("click", (event) => {
        event.stopPropagation();
        const box = document.getElementById(button.dataset.target);
        if (!box) {
            return;
        }

        const willOpen = box.classList.contains("toggle-box-hidden");
        box.classList.toggle("toggle-box-hidden", !willOpen);
        box.classList.toggle("toggle-box-open", willOpen);
        button.setAttribute("aria-expanded", String(willOpen));
    });

});

document.querySelectorAll(".stop-click").forEach((element) => {
    element.addEventListener("click", (event) => event.stopPropagation());
});

document.querySelectorAll("[data-context-action]").forEach((button) => {
    button.addEventListener("click", () => {
        const actions = {
            open: openSelectedFile,
            download: downloadSelectedFile,
            rename: renameSelectedFile,
            delete: deleteSelectedFile
        };
        actions[button.dataset.contextAction]?.();
    });
});

document.querySelector("[data-confirm-discard]")?.addEventListener(
    "click",
    (event) => {
        if (!window.confirm("Änderungen verwerfen?")) {
            event.preventDefault();
        }
    }
);

document.addEventListener("click", (event) => {
    if (!contextMenu?.contains(event.target)) {
        hideContextMenu();
    }
});

document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
        hideContextMenu();
    }
});
