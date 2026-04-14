const restaurantList = document.getElementById("restaurant-list");
const dishList = document.getElementById("dish-list");
const imageGrid = document.getElementById("image-grid");
const selectedRestaurantCard = document.getElementById("selected-restaurant-card");
const selectedRestaurantName = document.getElementById("selected-restaurant-name");
const selectedRestaurantAddress = document.getElementById("selected-restaurant-address");
const searchForm = document.getElementById("search-form");
const areaInput = document.getElementById("area_query");
const locationSuggestions = document.getElementById("location-suggestions");
const restaurantResultsContainer = document.getElementById("restaurant-results-container");
const changeRestaurantBtn = document.getElementById("change-restaurant-btn");

let selectedRestaurantId = null;
let displayedDishId = null;
let pendingDishId = null;
let hoverRequestToken = 0;
let hoverDebounceTimer = null;
const dishImageCache = new Map();

function setMessage(container, tagName, className, message) {
  container.innerHTML = "";
  const node = document.createElement(tagName);
  node.className = className;
  node.textContent = message;
  container.appendChild(node);
}

function buildRestaurantAddress(restaurant) {
  return [restaurant.address, `${restaurant.city} ${restaurant.postal_code}`.trim()]
    .filter(Boolean)
    .join(", ");
}

function clearUIAfterRestaurantChange() {
  dishList.innerHTML = "";
  imageGrid.innerHTML = "";
  selectedRestaurantCard.classList.add("hidden");
  selectedRestaurantName.textContent = "";
  selectedRestaurantAddress.textContent = "";
  displayedDishId = null;
  pendingDishId = null;
  dishImageCache.clear();
  if (hoverDebounceTimer) {
    clearTimeout(hoverDebounceTimer);
    hoverDebounceTimer = null;
  }
}

function showRestaurantResults() {
  restaurantResultsContainer.classList.remove("hidden");
  if (selectedRestaurantId) {
    selectedRestaurantCard.classList.add("hidden");
  }
}

function collapseRestaurantResults() {
  restaurantResultsContainer.classList.add("hidden");
  selectedRestaurantCard.classList.remove("hidden");
}

function buildQuery(params) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v) query.append(k, v);
  });
  return query.toString();
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "Request failed");
  }
  return response.json();
}

function renderRestaurants(restaurants) {
  restaurantList.innerHTML = "";
  if (!restaurants.length) {
    setMessage(restaurantList, "li", "hint", "No restaurants found.");
    return;
  }
  restaurants.forEach((r) => {
    const li = document.createElement("li");
    li.className = "card";
    const content = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = r.name;
    const lineBreak = document.createElement("br");
    const address = document.createElement("span");
    address.textContent = buildRestaurantAddress(r);
    content.appendChild(title);
    content.appendChild(lineBreak);
    content.appendChild(address);

    const button = document.createElement("button");
    button.dataset.id = r.id;
    button.dataset.name = r.name;
    button.dataset.address = r.address;
    button.dataset.city = r.city;
    button.dataset.postal = r.postal_code;
    button.textContent = "Choose";

    li.appendChild(content);
    li.appendChild(button);
    restaurantList.appendChild(li);
  });
}

function renderMenu(dishes) {
  dishList.innerHTML = "";
  if (!dishes.length) {
    setMessage(dishList, "li", "hint", "No menu data found for this restaurant.");
    return;
  }
  dishes.forEach((d) => {
    const li = document.createElement("li");
    li.className = "card dish-card";
    li.dataset.dishId = d.id;
    li.dataset.dishName = d.name;
    const content = document.createElement("div");
    content.className = "dish-card-content";
    const title = document.createElement("strong");
    title.textContent = d.name;
    content.appendChild(title);

    li.appendChild(content);
    dishList.appendChild(li);
  });
}

function setActiveDishCard(dishId) {
  dishList.querySelectorAll(".dish-card.active").forEach((card) => {
    if (card.dataset.dishId !== dishId) {
      card.classList.remove("active");
    }
  });
  if (!dishId) return;
  const activeCard = dishList.querySelector(`.dish-card[data-dish-id="${CSS.escape(dishId)}"]`);
  if (activeCard) {
    activeCard.classList.add("active");
  }
}

function renderImages(matches) {
  imageGrid.innerHTML = "";
  if (!matches.length) {
    setMessage(imageGrid, "p", "hint", "No images found.");
    return;
  }
  matches.forEach((m) => {
    const card = document.createElement("article");
    card.className = "img-card";
    const image = document.createElement("img");
    image.src = m.photo_url;
    image.alt = m.caption || "dish image";
    image.loading = "lazy";

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent =
      m.source === "serpapi"
        ? (m.caption || "Search result")
        : `score: ${m.score}${m.caption ? ` | ${m.caption}` : ""}`;

    card.appendChild(image);
    card.appendChild(meta);
    imageGrid.appendChild(card);
  });
}

async function loadDishImages(dishId, dishName = "") {
  if (!selectedRestaurantId || !dishId) return;
  if (dishId === displayedDishId || dishId === pendingDishId) return;

  const cacheKey = `${selectedRestaurantId}:${dishId}`;
  const cachedMatches = dishImageCache.get(cacheKey);
  if (cachedMatches) {
    setActiveDishCard(dishId);
    displayedDishId = dishId;
    pendingDishId = null;
    renderImages(cachedMatches);
    return;
  }

  pendingDishId = dishId;
  setActiveDishCard(dishId);
  const restaurantName = selectedRestaurantName.textContent.trim();
  const queryLabel = [restaurantName, dishName].filter(Boolean).join(" ");
  setMessage(imageGrid, "p", "hint", queryLabel ? `Searching images for ${queryLabel}...` : "Searching images...");
  const requestToken = ++hoverRequestToken;

  try {
    const data = await fetchJson(`/api/restaurants/${selectedRestaurantId}/dishes/${dishId}/images`);
    if (requestToken !== hoverRequestToken) return;
    displayedDishId = dishId;
    dishImageCache.set(cacheKey, data.matches);
    renderImages(data.matches);
  } catch (error) {
    if (requestToken !== hoverRequestToken) return;
    setMessage(imageGrid, "p", "error", error.message);
  } finally {
    if (requestToken === hoverRequestToken) {
      pendingDishId = null;
    }
  }
}

let suggestTimer = null;
areaInput.addEventListener("input", () => {
  if (suggestTimer) clearTimeout(suggestTimer);
  suggestTimer = setTimeout(async () => {
    const q = areaInput.value.trim();
    if (!q) {
      locationSuggestions.replaceChildren();
      return;
    }
    try {
      const data = await fetchJson(`/api/locations/suggest?q=${encodeURIComponent(q)}`);
      locationSuggestions.replaceChildren();
      (data.suggestions || []).forEach((value) => {
        const option = document.createElement("option");
        option.value = value;
        locationSuggestions.appendChild(option);
      });
    } catch (_) {
      // Keep typing smooth even when suggestions fail.
    }
  }, 250);
});

searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const area_query = document.getElementById("area_query").value.trim();
  const name = document.getElementById("restaurant_name").value.trim();
  if (!area_query || !name) {
    setMessage(restaurantList, "li", "error", "Please enter both area and restaurant name.");
    return;
  }
  const query = buildQuery({ area_query, name });

  setMessage(restaurantList, "li", "hint", "Searching...");
  clearUIAfterRestaurantChange();
  selectedRestaurantId = null;
  showRestaurantResults();

  try {
    const data = await fetchJson(`/api/restaurants/search?${query}`);
    renderRestaurants(data.restaurants);
  } catch (error) {
    setMessage(restaurantList, "li", "error", error.message);
  }
});

restaurantList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-id]");
  if (!button) return;

  selectedRestaurantId = button.dataset.id;
  const selectedName = button.dataset.name;
  const selectedAddress = `${button.dataset.address}, ${button.dataset.city} ${button.dataset.postal}`.trim();
  selectedRestaurantName.textContent = selectedName;
  selectedRestaurantAddress.textContent = selectedAddress;
  selectedRestaurantCard.classList.remove("hidden");
  setMessage(dishList, "li", "hint", "Loading menu...");
  imageGrid.innerHTML = "";
  collapseRestaurantResults();

  try {
    const menu = await fetchJson(`/api/restaurants/${selectedRestaurantId}/menu`);
    renderMenu(menu.dishes);
  } catch (error) {
    setMessage(dishList, "li", "error", error.message);
  }
});

changeRestaurantBtn.addEventListener("click", () => {
  showRestaurantResults();
});

dishList.addEventListener("mouseover", async (event) => {
  const dishCard = event.target.closest(".dish-card[data-dish-id]");
  if (!dishCard || !selectedRestaurantId) return;
  if (dishCard.contains(event.relatedTarget)) return;
  if (hoverDebounceTimer) {
    clearTimeout(hoverDebounceTimer);
  }
  hoverDebounceTimer = setTimeout(() => {
    loadDishImages(dishCard.dataset.dishId, dishCard.dataset.dishName);
  }, 220);
});
