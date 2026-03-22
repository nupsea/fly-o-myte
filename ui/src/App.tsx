/**
 * App root — slim router shell.
 * All views and components live in their own modules.
 */
import { Routes, Route, useLocation } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import Sidebar from './components/Sidebar'
import Dashboard from './views/Dashboard'
import Scout from './views/Scout'
import Monitoring from './views/Monitoring'
import Profile from './views/Profile'
import Planner from './views/Planner'
import Analytics from './views/Analytics'
import './App.css'

function App() {
  const location = useLocation();
  return (
    <div className="app-container">
      <Sidebar />
      <main className="content">
        <AnimatePresence mode="wait">
          <Routes location={location} key={location.pathname}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/scout" element={<Scout />} />
            <Route path="/planner" element={<Planner />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/monitoring" element={<Monitoring />} />
            <Route path="/profile" element={<Profile />} />
          </Routes>
        </AnimatePresence>
      </main>
    </div>
  );
}

export default App;
