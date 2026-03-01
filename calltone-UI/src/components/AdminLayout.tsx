import { Outlet } from "react-router-dom";
import AdminSidebar from "@/components/AdminSidebar";
import AdminMobileNav from "@/components/AdminMobileNav";
import AnimatedBackground from "@/components/AnimatedBackground";
import PageTransition from "@/components/PageTransition";

const AdminLayout = () => {
  return (
    <PageTransition>
      <div className="min-h-screen relative flex">
        <AnimatedBackground />
        {/* Desktop sidebar */}
        <div className="hidden md:block">
          <AdminSidebar />
        </div>
        {/* Mobile top nav */}
        <div className="md:hidden fixed top-0 left-0 right-0 z-50">
          <AdminMobileNav />
        </div>
        {/* Main content */}
        <main className="flex-1 min-w-0 md:max-h-screen md:overflow-y-auto">
          <div className="max-w-7xl mx-auto px-5 sm:px-8 py-8 sm:py-12 md:pt-12 pt-20">
            <Outlet />
          </div>
        </main>
      </div>
    </PageTransition>
  );
};

export default AdminLayout;
