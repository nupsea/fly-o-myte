/**
 * Sidebar navigation component.
 */
import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Search,
  Sparkles,
  Activity,
  Users,
  Plane,
  BarChart
} from 'lucide-react'

const Sidebar = () => {
  const navItems = [
    { to: "/", icon: LayoutDashboard, label: "Dashboard" },
    { to: "/scout", icon: Search, label: "Smart Scout" },
    { to: "/analytics", icon: BarChart, label: "Analytics" },
    { to: "/planner", icon: Sparkles, label: "AI Planner" },
    { to: "/monitoring", icon: Activity, label: "Monitoring" },
    { to: "/profile", icon: Users, label: "Family Profile" },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="logo-container">
          <Plane className="logo-icon" />
          <span className="logo-text">Fly-O-Myte</span>
        </div>
      </div>
      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <NavLink 
            key={item.to} 
            to={item.to} 
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          >
            <item.icon className="nav-icon" size={20} />
            <span className="nav-label">{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-footer">
        <div className="profile-mini">
          <div className="avatar">B</div>
          <div className="profile-info">
            <span className="profile-name">Brisbane Family</span>
            <span className="profile-status">Premium</span>
          </div>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
