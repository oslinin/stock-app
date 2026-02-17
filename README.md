# Stock App

Based on the article: [Build & Publish Your First Stock App for FREE](https://medium.com/@wl8380/build-publish-your-first-stock-app-for-free-df59820998aa?sk=655af74c972a5fd37ca0ba0d0133d264)

This project was bootstrapped with [Create React App](https://github.com/facebook/create-react-app).

A simple React application to fetch and display real-time stock data using the Alpha Vantage API.

## Project Overview

This project is a stock price tracker that allows users to enter a stock symbol (e.g., AAPL, TSLA) and retrieve the latest price and change percentage.

## Source Files

- `src/App.js`: The main component of the application. It contains the logic for fetching data from the Alpha Vantage API using `axios`, managing state for the search symbol and stock data, and rendering the UI.
- `src/App.css`: Defines the styling for the main application and the stock information cards.
- `src/index.js`: The entry point for the React application which mounts the `App` component to the DOM.
- `src/index.css`: Contains global styles for the application.
- `public/index.html`: The base HTML template where the React app is injected.

## Key Dependencies

- **React**: Used for building the component-based user interface.
- **Axios**: A promise-based HTTP client for making API requests to Alpha Vantage.
- **Chart.js** & **react-chartjs-2**: Installed dependencies intended for future data visualization features.

## Available Scripts

In the project directory, you can run:

- `pnpm start`: Runs the app in development mode at [http://localhost:3000](http://localhost:3000).
- `pnpm run build`: Builds the app for production to the `build` folder.
- `pnpm run publish`: Builds and updates the `docs/` folder for GitHub Pages deployment.
- `pnpm run deploy`: Deploys the application to the `gh-pages` branch using the `build/` folder.
