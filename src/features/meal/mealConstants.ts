/**
 * Meal System Constants
 * 
 * Assets for player meals and Monika's meal choices during "Eat Together" mode
 */

// Player meal assets (what the user can eat)
export const EAT_MEAL_ASSETS = {
  pizza: "/vn/monika/t/food/food_pizza.png",
  sushi: "/vn/monika/t/food/food_sushi.png",
  pasta: "/vn/monika/t/food/food_pasta.png",
  salad: "/vn/monika/t/food/food_salad.png",
  burger: "/vn/monika/t/food/food_burger.png",
  pierogi: "/vn/monika/t/food/food_pierogi.png",
  cereal: "/vn/monika/t/food/food_cereal.png",
  coffee: "/vn/monika/t/food/drink_coffee.png",
  tea: "/vn/monika/t/food/drink_tea.png",
  finished: "/vn/monika/t/food/food_finished.png",
};

// Monika's available meal choices
export const MONIKA_MEAL_ASSETS = {
  pasta: "/vn/monika/t/food/food_pasta.png",
  salad: "/vn/monika/t/food/food_salad.png",
  sushi: "/vn/monika/t/food/food_sushi.png",
  pierogi: "/vn/monika/t/food/food_pierogi.png",
  cereal: "/vn/monika/t/food/food_cereal.png",
};

// Keywords for detecting meal types in text (English + Polish)
export const MEAL_KEYWORDS = [
  { key: "pizza", re: /\b(pizza(s)?|piz(z)?a)\b/ },
  { key: "sushi", re: /\b(sushi)\b/ },
  { key: "pasta", re: /\b(pasta|spaghetti|ramen|noodles?|makaron)\b/ },
  { key: "salad", re: /\b(salad|salat|sałatka|salatka)\b/ },
  { key: "burger", re: /\b(burger|cheeseburger|hamburger)\b/ },
  { key: "pierogi", re: /\b(pierogi|pierog(i|ów|ow)?)\b/ },
  { key: "cereal", re: /\b(cereal|płatki|platki)\b/ },
  { key: "coffee", re: /\b(coffee|kawa)\b/ },
  { key: "tea", re: /\b(tea|herbata)\b/ },
];

// Keywords for detecting meal completion (English + Polish)
export const FINISHED_MEAL_KEYWORDS = [
  /\b(finished eating|done eating|i'?m full|i am full)\b/,
  /\b(sko[ńn]czy[łl](em|am)?(em)?(\s+je[śs]?[cć])?)\b/,
  /\b(zjad(łem|lam))\b/,
  /\b(najedzon(y|a))\b/,
  /\b(syt(y|a))\b/,
];

// Keywords for starting "Eat Together" mode (English + Polish)
export const START_EAT_TOGETHER_KEYWORDS = [
  "eat together",
  "let's eat",
  "lets eat",
  "dinner together",
  "have dinner",
  "have lunch",
  "have breakfast",
  "meal together",
  "jedzmy razem",
  "zjedzmy razem",
  "kolacja razem",
  "obiad razem",
  "sniadanie razem",
  "śniadanie razem",
  "chodzmy na obiad",
  "chodźmy na obiad",
  "chodzmy na kolacje",
  "chodźmy na kolację",
];

// Keywords for stopping "Eat Together" mode (English + Polish)
export const STOP_EAT_TOGETHER_KEYWORDS = [
  "end meal",
  "end eating",
  "end dinner",
  "end lunch",
  "stop eat together",
  "stop eating together",
  "finish eating",
  "that's all",
  "thats all",
  "wrap up dinner",
  "koniec trybu jedzenia",
  "koniec trybu",
  "koniec posilku",
  "koniec posiłku",
  "zakończ posiłek",
  "zakoncz posilek",
];

// Default Monika's meal when starting "Eat Together"
export const DEFAULT_MONIKA_MEAL = "pasta";
