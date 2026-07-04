import { Route, Routes } from "react-router-dom";
import { AppDataProvider } from "./context/AppDataContext";
import { LocationProvider } from "./context/LocationContext";
import { ChatScreen } from "./screens/ChatScreen";
import { HomeScreen } from "./screens/HomeScreen";

export default function App() {
  return (
    <LocationProvider>
      <AppDataProvider>
        <Routes>
          <Route path="/" element={<HomeScreen />} />
          <Route path="/chat/:agentId" element={<ChatScreen />} />
        </Routes>
      </AppDataProvider>
    </LocationProvider>
  );
}
