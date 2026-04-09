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

function clearUIAfterRestaurantChange() {
  dishList.innerHTML = "";
  imageGrid.innerHTML = "";
  selectedRestaurantCard.classList.add("hidden");
  selectedRestaurantName.textContent = "";
  selectedRestaurantAddress.textContent = "";
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
    restaurantList.innerHTML = "<li class='hint'>No restaurants found.</li>";
    return;
  }
  restaurants.forEach((r) => {
    const li = document.createElement("li");
    li.className = "card";
    li.innerHTML = `
      <div>
        <strong>${r.name}</strong><br>
        <span>${r.address}, ${r.city} ${r.postal_code}</span>
      </div>
      <button data-id="${r.id}" data-name="${r.name}" data-address="${r.address}" data-city="${r.city}" data-postal="${r.postal_code}">Choose</button>
    `;
    restaurantList.appendChild(li);
  });
}

function renderMenu(dishes) {
  dishList.innerHTML = "";
  if (!dishes.length) {
    dishList.innerHTML = "<li class='hint'>No menu data found for this restaurant.</li>";
    return;
  }
  dishes.forEach((d) => {
    const li = document.createElement("li");
    li.className = "card";
    li.innerHTML = `
      <div>
        <strong>${d.name}</strong><br>
        <span>${d.description || "No description"}</span>
      </div>
      <button data-dish-id="${d.id}" data-dish-name="${d.name}">Match Images</button>
    `;
    dishList.appendChild(li);
  });
}

function renderImages(matches) {
  imageGrid.innerHTML = "";
  if (!matches.length) {
    imageGrid.innerHTML = "<p class='hint'>No images found.</p>";
    return;
  }
  matches.forEach((m) => {
    const card = document.createElement("article");
    card.className = "img-card";
    card.innerHTML = `
      <img src="${m.photo_url}" alt="${m.caption || "dish image"}" loading="lazy" />
      <div class="meta">score: ${m.score} ${m.caption ? `| ${m.caption}` : ""}</div>
    `;
    imageGrid.appendChild(card);
  });
}

let suggestTimer = null;
areaInput.addEventListener("input", () => {
  if (suggestTimer) clearTimeout(suggestTimer);
  suggestTimer = setTimeout(async () => {
    const q = areaInput.value.trim();
    if (!q) {
      locationSuggestions.innerHTML = "";
      return;
    }
    try {
      const data = await fetchJson(`/api/locations/suggest?q=${encodeURIComponent(q)}`);
      locationSuggestions.innerHTML = "";
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
    restaurantList.innerHTML = "<li class='error'>Please enter both area and restaurant name.</li>";
    return;
  }
  const query = buildQuery({ area_query, name });

  restaurantList.innerHTML = "<li class='hint'>Searching...</li>";
  clearUIAfterRestaurantChange();
  selectedRestaurantId = null;
  showRestaurantResults();

  try {
    const data = await fetchJson(`/api/restaurants/search?${query}`);
    renderRestaurants(data.restaurants);
  } catch (error) {
    restaurantList.innerHTML = `<li class='error'>${error.message}</li>`;
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
  dishList.innerHTML = "<li class='hint'>Loading menu...</li>";
  imageGrid.innerHTML = "";
  collapseRestaurantResults();

  try {
    const menu = await fetchJson(`/api/restaurants/${selectedRestaurantId}/menu`);
    renderMenu(menu.dishes);
  } catch (error) {
    dishList.innerHTML = `<li class='error'>${error.message}</li>`;
  }
});

changeRestaurantBtn.addEventListener("click", () => {
  showRestaurantResults();
});

dishList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-dish-id]");
  if (!button || !selectedRestaurantId) return;
  const dishId = button.dataset.dishId;
  imageGrid.innerHTML = "<p class='hint'>Matching images...</p>";
  try {
    const data = await fetchJson(`/api/restaurants/${selectedRestaurantId}/dishes/${dishId}/images`);
    renderImages(data.matches);
  } catch (error) {
    imageGrid.innerHTML = `<p class='error'>${error.message}</p>`;
  }
});
