import os
import rospy
import rospkg
import collections
import time
import sys
import subprocess
import numpy as np
from qt_gui.plugin import Plugin
from python_qt_binding import loadUi
from python_qt_binding.QtWidgets import QWidget, QDialog
from python_qt_binding.QtCore import QMutex, QMutexLocker,QSemaphore, QThread
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from execute_gui_steps import GUI_Step_Executor
from rpi_arm_composites_manufacturing_gui.msg import GUIStepAction, GUIStepGoal




from safe_kinematic_controller.msg import ControllerState as controllerstate
from safe_kinematic_controller.srv import SetControllerMode, SetControllerModeRequest
from rpi_arm_composites_manufacturing_process.msg import ProcessStepAction, ProcessStepGoal, ProcessState, ProcessStepFeedback
import actionlib
from rqt_console import console_widget
from rqt_console import message_proxy_model
from rqt_plot import plot
import rosservice
import rviz
import safe_kinematic_controller.ros.commander as controller_commander_pkg
from panel_selector_window import PanelSelectorWindow
from user_authentication_window import UserAuthenticationWindow
#TODO Integrate pyqtgraph into automatic package download
import pyqtgraph as pg
import threading
'''
freeBytes=QSemaphore(100)
usedBytes=QSemaphore()
consoleData=collections.deque(maxlen=200)
'''
class LEDIndicator(QAbstractButton):
    scaledSize=1000.0
    def __init__(self):
        QAbstractButton.__init__(self)
        self.setMinimumSize(24, 24)
        self.setCheckable(True)
        # Green
        self.on_color_1 = QColor(0, 255, 0)
        self.on_color_2 = QColor(0, 192, 0)
        self.off_color_1 = QColor(255, 0, 0)
        self.off_color_2 = QColor(128, 0, 0)

    def resizeEvent(self, QResizeEvent):
        self.update()

    def paintEvent(self, QPaintEvent):
        realSize = min(self.width(), self.height())

        painter = QPainter(self)
        pen = QPen(Qt.black)
        pen.setWidth(1)

        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(realSize / self.scaledSize, realSize / self.scaledSize)

        gradient = QRadialGradient(QPointF(-500, -500), 1500, QPointF(-500, -500))
        gradient.setColorAt(0, QColor(224, 224, 224))
        gradient.setColorAt(1, QColor(28, 28, 28))
        painter.setPen(pen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(0, 0), 500, 500)

        gradient = QRadialGradient(QPointF(500, 500), 1500, QPointF(500, 500))
        gradient.setColorAt(0, QColor(224, 224, 224))
        gradient.setColorAt(1, QColor(28, 28, 28))
        painter.setPen(pen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(0, 0), 450, 450)

        painter.setPen(pen)
        if self.isChecked():
            gradient = QRadialGradient(QPointF(-500, -500), 1500, QPointF(-500, -500))
            gradient.setColorAt(0, self.on_color_1)
            gradient.setColorAt(1, self.on_color_2)
        else:
            gradient = QRadialGradient(QPointF(500, 500), 1500, QPointF(500, 500))
            gradient.setColorAt(0, self.off_color_1)
            gradient.setColorAt(1, self.off_color_2)

        painter.setBrush(gradient)
        painter.drawEllipse(QPointF(0, 0), 400, 400)

    @pyqtProperty(QColor)
    def onColor1(self):
        return self.on_color_1

    @onColor1.setter
    def onColor1(self, color):
        self.on_color_1 = color

    @pyqtProperty(QColor)
    def onColor2(self):
        return self.on_color_2

    @onColor2.setter
    def onColor2(self, color):
        self.on_ciagnosticscreen.backToRun.pressed.connect(self._to_run_screen)
        #self._runscolor_2 = color

    @pyqtProperty(QColor)
    def offColor1(self):
        return self.off_color_1

    @offColor1.setter
    def offColor1(self, color):
        self.off_color_1 = color

    @pyqtProperty(QColor)
    def offColor2(self):
        return self.off_color_2

    @offColor2.setter
    def offColor2(self, color):
        self.off_color_2 = color


class VacuumConfirm(QWidget):
    def __init__(self):
        super(VacuumConfirm,self).__init__()

class ConsoleThread(QThread):
    def __init__(self,State_info):
		super(ConsoleThread,self).__init__()
		self.State_info=State_info

    def run(self):
		while(True):
			usedBytes.acquire()
			dataval=consoleData.pop()
			self.State_info.addItem(dataval)
			self.State_info.scrollToBottom()
			#print dataval
			freeBytes.release()

class RQTPlotWindow(QMainWindow):
    def __init__(self, parent=None):
        super(RQTPlotWindow, self).__init__(None)
        self.rqtgraph=plot.Plot(parent)



class ExperimentGUI(Plugin):

    def __init__(self, context):
        super(ExperimentGUI, self).__init__(context)
        # Give QObjects reasonable names
        self.plans=['Starting Position','Above Panel', 'Panel Grabbed','Above Placement Nest','Panel Placed']
        #state_dict ties each state to planlistindex values
        #self.state_dict={'reset_position':0,'pickup_prepare':1,'pickup_lower':2,'pickup_grab_first_step':2,'pickup_grab_second_step':2,'pickup_raise':2,'transport_panel':3,'place_lower':4,'place_set_first_step':4,'place_set_second_step':4,'place_raise':4}
        self.gui_execute_states=["reset","panel_pickup","pickup_grab","transport_panel","place_panel"]
        self.execute_states=[['plan_to_reset_position','move_to_reset_position'],['plan_pickup_prepare','move_pickup_prepare'],['plan_pickup_lower','move_pickup_lower','plan_pickup_grab_first_step','move_pickup_grab_first_step','plan_pickup_grab_second_step','move_pickup_grab_second_step','plan_pickup_raise','move_pickup_raise'],
                            ['plan_transport_payload','move_transport_payload'],['plan_place_set_second_step']]
        self.teleop_modes=['Error','Off','Joint','Cartesian','Cylindrical','Spherical']
        self.current_teleop_mode=1
        self.teleop_button_string="Tele-op\nMode:\n"
        self.setObjectName('MyPlugin')
        self._lock=threading.Lock()
        #self._send_event=threading.Event()
        self.controller_commander=controller_commander_pkg.ControllerCommander()
        # Process standalone plugin command-line arguments
        from argparse import ArgumentParser
        parser = ArgumentParser()
        # Add argument(s) to the parser.
        parser.add_argument("-q", "--quiet", action="store_true",
                      dest="quiet",
                      help="Put plugin in silent mode")
        args, unknowns = parser.parse_known_args(context.argv())
        if not args.quiet:
            print 'arguments: ', args
            print 'unknowns: ', unknowns

        # Create QWidget
        self.in_process=None
        self.recover_from_pause=False

        #rospy.get_param("rosbag_name")
        #<param name="start_time" command="date +'%d-%m-%Y_%Ih%Mm%S'"/>
        #rosbag record args="record -O arg('start_time')

        
        self._mainwidget = QWidget()
        self.layout = QGridLayout()
        self._mainwidget.setLayout(self.layout)
        self.disconnectreturnoption=False
        self.stackedWidget=QStackedWidget()#self._mainwidget)
        self.layout.addWidget(self.stackedWidget,0,0)
        self._welcomescreen=QWidget()
        self._runscreen=QWidget()
        self._errordiagnosticscreen=QWidget()
        self.stackedWidget.addWidget(self._welcomescreen)
        self.stackedWidget.addWidget(self._runscreen)
        self.stackedWidget.addWidget(self._errordiagnosticscreen)
        #self._data_array=collections.deque(maxlen=500)
        self._proxy_model=message_proxy_model.MessageProxyModel()
        self._rospack=rospkg.RosPack()
        #self.console=console_widget.ConsoleWidget(self._proxy_model,self._rospack)
        self.robotconnectionled=LEDIndicator()
        self.robotconnectionled.setDisabled(True)  # Make the led non clickable
        self.forcetorqueled=LEDIndicator()
        self.forcetorqueled.setDisabled(True)  # Make the led non clickable
        self.overheadcameraled=LEDIndicator()
        self.overheadcameraled.setDisabled(True)  # Make the led non clickable
        self.grippercameraled=LEDIndicator()
        self.grippercameraled.setDisabled(True)  # Make the led non clickable
        self.runscreenstatusled=LEDIndicator()
        self.runscreenstatusled.setDisabled(True) 
        
        self.step_executor=GUI_Step_Executor()
        self.step_executor.error_signal.connect(self._feedback_receive)
        #self.step_executor.error_function=self._feedback_receive
        #Need this to pause motions
        self.process_client=actionlib.ActionClient('process_step', ProcessStepAction)
        self.process_client.wait_for_server()
        self.placement_targets={'leeward_mid_panel':'panel_nest_leeward_mid_panel_target','leeward_tip_panel':'panel_nest_leeward_tip_panel_target'}
        self.placement_target='panel_nest_leeward_mid_panel_target'
        
        self.panel_type='leeward_mid_panel'
        self.client_handle=None
        
        service_list=rosservice.get_service_list()
        if('/overhead_camera/trigger' in service_list):
            self.led_change(self.overheadcameraled,True)
        else:
            self.led_change(self.overheadcameraled,False)
        if('/gripper_camera_2/trigger' in service_list):
            self.led_change(self.grippercameraled,True)
        else:
            self.led_change(self.grippercameraled,False)

        self.mode=0
        #self.rewound=False
        self.count=0
        self.data_count=0
        self.force_torque_data=np.zeros((6,1))
        self.joint_angle_data=np.zeros((6,1))
        # Get path to UI file which should be in the "resource" folder of this package
        self.welcomescreenui = os.path.join(rospkg.RosPack().get_path('rpi_arm_composites_manufacturing_gui'), 'resource', 'welcomeconnectionscreen.ui')
        self.runscreenui = os.path.join(rospkg.RosPack().get_path('rpi_arm_composites_manufacturing_gui'), 'resource', 'Runscreen.ui')
        self.errorscreenui = os.path.join(rospkg.RosPack().get_path('rpi_arm_composites_manufacturing_gui'), 'resource', 'errordiagnosticscreen.ui')
        self.rewound=False

        # Extend the widget with all attributes and children from UI file
        loadUi(self.welcomescreenui, self._welcomescreen)
        loadUi(self.runscreenui, self._runscreen)
        loadUi(self.errorscreenui,self._errordiagnosticscreen)
        # Give QObjects reasonable names
        self._mainwidget.setObjectName('MyPluginUi')
        # Show _widget.windowTitle on left-top of each plugin (when
        # it's set in _widget). This is useful when you open multiple
        # plugins at once. Also if you open multiple instances of your
        # plugin at once, these lines add number to make it easy to
        # tell from pane to pane.
        if context.serial_number() > 1:
            self._mainwidget.setWindowTitle(self._mainwidget.windowTitle() + (' (%d)' % context.serial_number()))

        context.add_widget(self._mainwidget)
        self.context=context

        self.plugin_settings=None
        self.instance_settings=None
        #self._errordiagnosticscreen.consoleWidget=console_widget.ConsoleWidget(self._proxy_model,self._rospack)
        #####consoleiagnosticscreen.backToRun.pressed.connect(self._to_run_screen)
        #self._runscThread=ConsoleThread(self._widget.State_info)
       # self._welcomescreen.statusFormLayout.takeAt(0)
        self._welcomescreen.statusFormLayout.addWidget(self.robotconnectionled,0,0)
        self._welcomescreen.statusFormLayout.addWidget(self.forcetorqueled,2,0)
        self._welcomescreen.statusFormLayout.addWidget(self.overheadcameraled,4,0)
        self._welcomescreen.statusFormLayout.addWidget(self.grippercameraled,6,0)
        self._runscreen.connectionLayout.addWidget(self.runscreenstatusled,0,1)
        #self._welcomescreen.robotConnectionWidget.addWidget(self.led)
        #consoleThread.finished.connect(app.exit)

        #####consoleThread.start()
        self.rviz_starter=os.path.join(rospkg.RosPack().get_path('rpi_arm_composites_manufacturing_gui'), 'src', 'rpi_arm_composites_manufacturing_gui', 'rviz_starter.py')

        # Add widget to the user interface
        #context.add_widget(console)==QDialog.Accepted
            #context.add_widget(rqt_console)

        for entry in self.plans:
            listentry=QListWidgetItem(entry)
            listentry.setFlags(Qt.ItemIsSelectable)
            self._runscreen.planList.addItem(listentry)

        self._runscreen.planList.item(0).setSelected(True)
        self.planListIndex=0
        self._runscreen.panelType.setText(self.panel_type)
        self._runscreen.placementNestTarget.setText("Leeward Mid Panel Nest")

        self._runscreen.panelType.setReadOnly(True)
        self._runscreen.placementNestTarget.setReadOnly(True)
        self.commands_sent=False
        rospy.Subscriber("controller_state", controllerstate, self.callback)
        self._set_controller_mode=rospy.ServiceProxy("set_controller_mode",SetControllerMode)
        rospy.Subscriber("GUI_state", ProcessState, self.process_state_set)
        #rospy.Subscriber('gui_error', String, self._feedback_receive())
        self.force_torque_plot_widget=QWidget()
        self.joint_angle_plot_widget=QWidget()
        self._welcomescreen.openConfig.clicked.connect(self._open_config_options)
        #self._welcomescreen.openAdvancedOptions.pressed.connect(self._open_login_prompt)
        self._welcomescreen.toRunScreen.pressed.connect(self._to_run_screen)
        self._runscreen.backToWelcome.pressed.connect(self._to_welcome_screen)
        #self._runscreen.toErrorScreen.pressed.connect(self._to_error_screen)
        self._runscreen.nextPlan.pressed.connect(self._next_plan)
        self._runscreen.previousPlan.pressed.connect(self._previousPlan)
        self._runscreen.resetToHome.pressed.connect(self._reset_position)
        self._runscreen.stopPlan.pressed.connect(self._stopPlan)
        self._runscreen.accessTeleop.pressed.connect(self.change_teleop_modes)
        #self._errordiagnosticscreen.openOverheadCameraView.pressed.connect(self._open_overhead_camera_view)
        #self._errordiagnosticscreen.openGripperCameraViews.pressed.connect(self._open_gripper_camera_views)
        self._errordiagnosticscreen.openForceTorqueDataPlot.pressed.connect(self._open_force_torque_data_plot)
        self._errordiagnosticscreen.openJointAngleDataPlot.pressed.connect(self._open_joint_angle_data_plot)
        self._errordiagnosticscreen.backToRun.pressed.connect(self._to_run_screen)
        #self._runscreen.widget.frame=rviz.VisualizationFrame()
        #self._runscreen.widget.frame.setSplashPath( "" )


        ## VisualizationFrame.initialize() must be called before
        ## VisualizationFrame.load().  In fact it must be called
        ## before most interactions with RViz classes because it
        ## instantiates and initializes the VisualizationManager,
        ## which is the central class of RViz.
        #self._runscreen.widget.frame.initialize()
        #self.manager = self._runscreen.widget.frame.getManager()


#        self._welcomescreen.openAdvancedOptions.pressed.connect(self._open_advanced_options)

    def led_change(self,led,state):
        led.setChecked(state)

    def _to_welcome_screen(self):
        self.stackedWidget.setCurrentIndex(0)

    def _to_run_screen(self):
        self.controller_commander.set_controller_mode(self.controller_commander.MODE_HALT,1,[],[])
        if(self.stackedWidget.currentIndex()==0):
            self.messagewindow=PanelSelectorWindow()
            self.messagewindow.show()
            self.messagewindow.setFixedSize(self.messagewindow.size())
            if self.messagewindow.exec_():
                next_selected_panel=self.messagewindow.get_panel_selected()
                if(next_selected_panel != None):
                    self.panel_type=next_selected_panel
                    self.placement_target=self.placement_targets[self.panel_type]

        self.stackedWidget.setCurrentIndex(1)
        self._runscreen.panelType.setText(self.panel_type)
        if(self.panel_type=='leeward_mid_panel'):
            self._runscreen.placementNestTarget.setText("Leeward Mid Panel Nest")
        elif(self.panel_type=='leeward_tip_panel'):
            self._runscreen.placementNestTarget.setText("Leeward Tip Panel Nest")
        else:
            raise Exception('Unknown panel type selected')


    def _to_error_screen(self):
        self.stackedWidget.setCurrentIndex(2)

    def _login_prompt(self):
        self.loginprompt=UserAuthenticationWindow()
        if self.loginprompt.exec_():
            #self.loginprompt.show()
        #while(not self.loginprompt.returned):
            #pass

            return True
        else:
            return False






    def _open_config_options(self):
        if(self._login_prompt()):
            self.led_change(self.robotconnectionled,True)


    #def _open_overhead_camera_view(self):


    #def _open_gripper_camera_views(self):



    def _open_force_torque_data_plot(self):
        self.plot_container=[]
        self.x_data = np.arange(1)

        self.force_torque_app=QApplication([])

        self.force_torque_plot_widget=pg.plot()
        self.force_torque_plot_widget.addLegend()
        #self.layout.addWidget(self.force_torque_plot_widget,0,1)

        self.force_torque_plot_widget.showGrid(x=True, y=True)
        self.force_torque_plot_widget.setLabel('left','Force/Torque','N/N*m')
        self.force_torque_plot_widget.setLabel('bottom','Sample Number','n')

        self.plot_container.append(self.force_torque_plot_widget.plot(pen=(255,0,0),name="Torque X"))
        self.plot_container.append(self.force_torque_plot_widget.plot(pen=(0,255,0),name="Torque Y"))
        self.plot_container.append(self.force_torque_plot_widget.plot(pen=(0,0,255),name="Torque Z"))
        self.plot_container.append(self.force_torque_plot_widget.plot(pen=(255,255,0),name="Force X"))
        self.plot_container.append(self.force_torque_plot_widget.plot(pen=(0,255,255),name="Force Y"))
        self.plot_container.append(self.force_torque_plot_widget.plot(pen=(255,0,255),name="Force Z"))


        #self.force_torque_plotter=PlotManager(title='Force Torque Data',nline=3,widget=self.force_torque_plot_widget)
        #self.force_torque_plot_widget.show()

        #self.force_torque_plotter.add("Hello", np.arange(10))
        #self.force_torque_plotter.update()


        #self.rosGraph.show()
        #self.rosGraph.exec_()
    def _open_joint_angle_data_plot(self):
        self.plot_container=[]
        self.x_data = np.arange(1)

        self.joint_angle_app=QApplication([])

        self.joint_angle_plot_widget=pg.plot()
        self.joint_angle_plot_widget.addLegend()
        #self.layout.addWidget(self.joint_angle_plot_widget,0,1)

        self.joint_angle_plot_widget.showGrid(x=True, y=True)
        self.joint_angle_plot_widget.setLabel('left','Force/Torque','N/N*m')
        self.joint_angle_plot_widget.setLabel('bottom','Sample Number','n')

        self.plot_container.append(self.joint_angle_plot_widget.plot(pen=(255,0,0),name="Joint 1"))
        self.plot_container.append(self.joint_angle_plot_widget.plot(pen=(0,255,0),name="Joint 2"))
        self.plot_container.append(self.joint_angle_plot_widget.plot(pen=(0,0,255),name="Joint 3"))
        self.plot_container.append(self.joint_angle_plot_widget.plot(pen=(255,255,0),name="Joint 4"))
        self.plot_container.append(self.joint_angle_plot_widget.plot(pen=(0,255,255),name="Joint 5"))
        self.plot_container.append(self.joint_angle_plot_widget.plot(pen=(255,0,255),name="Joint 6"))
        self.plot_container.append(self.joint_angle_plot_widget.plot(pen=(255,255,255),name="Joint 7"))


    def _open_rviz_prompt(self):
        subprocess.Popen(['python', self.rviz_starter])
#    def _open_advanced_options(self):
#        main = Main()
#        sys.exit(main.main(sys.argv, standalone='rqt_rviz/RViz', plugin_argument_provider=add_arguments))

    def _raise_rviz_window(self):
        subprocess.call(["xdotool", "search", "--name", "rviz", "windowraise"])

    def _next_plan(self):
    #TODO: Disable previous plan if planListIndex==2 or 4
        self._runscreen.nextPlan.setDisabled(True)
        self._runscreen.previousPlan.setDisabled(True)
        self._runscreen.resetToHome.setDisabled(True)
        self.reset_teleop_button()
        #TODO Make it change color when in motion
        if(self.planListIndex+1==self._runscreen.planList.count()):
            self.planListIndex=0
        elif(self.recover_from_pause):
            self.recover_from_pause=False
        else:
            self.planListIndex+=1
        #g=GUIStepGoal(self.gui_execute_states[self.planListIndex], self.panel_type)
        #self.client_handle=self.client.send_goal(g,done_cb=self._process_done,feedback_cb=self._feedback_receive)
        
        self.step_executor._nextPlan(self.panel_type,self.planListIndex,self.placement_target)

        self._runscreen.planList.item(self.planListIndex).setSelected(True)
        if(self.rewound):
            self.rewound=False
            self._runscreen.previousPlan.setDisabled(False)
        
            """
            self._runscreen.vacuum.setText("OFF")
            self._runscreen.panel.setText("Detached")
            self._runscreen.panelTag.setText("Not Localized")
            self._runscreen.nestTag.setText("Not Localized")
            self._runscreen.overheadCamera.setText("OFF")
            self._runscreen.gripperCamera.setText("OFF")
            self._runscreen.forceSensor.setText("Biased to 0")
            self._runscreen.pressureSensor.setText("[0,0,0]")
            """
        '''
        elif(self.planListIndex==1):
            self.send_thread=threading.Thread(target=self._execute_steps,args=(1,self.last_step, self.panel_type,0))
            rospy.loginfo("thread_started")
            self.send_thread.setDaemon(True)
            self.send_thread.start()
            self._send_event.set()
            #self._execute_step('plan_pickup_prepare',self.panel_type)
            #self._execute_step('move_pickup_prepare')'''"""
            self._runscreen.vacuum.setText("OFF")
            self._runscreen.panel.setText("Detached")
            self._runscreen.panelTag.setText("Localized")
            self._runscreen.nestTag.setText("Not Localized")
            self._runscreen.overheadCamera.setText("ON")
            self._runscreen.gripperCamera.setText("OFF")
            self._runscreen.forceSensor.setText("ON")
            self._runscreen.pressureSensor.setText("[0,0,0]")
            """"""
        elif(self.planListIndex==2):
            
            self.send_thread=threading.Thread(target=self._execute_steps,args=(2,self.last_step))
            self.send_thread.setDaemon(True)
            self.send_thread.start()
            self._send_event.set()""""""
            self._execute_step('plan_pickup_lower')
            self._execute_step('move_pickup_lower')
            self._execute_step('plan_pickup_grab_first_step')
            self._execute_step('move_pickup_grab_first_step')
            self._execute_step('plan_pickup_grab_second_step')
            self._execute_step('move_pickup_grab_second_step')
            self._execute_step('plan_pickup_raise')
            self._execute_step('move_pickup_raise')

            self._runscreen.vacuum.setText("OFF")
            self._runscreen.panel.setText("Detached")
            self._runscreen.panelTag.setText("Localized")self.controller_commander=controller_commander_pkg.arm_composites_manufacturing_controller_commander()
            self._runscreen.nestTag.setText("Not Localized")
            self._runscreen.overheadCamera.setText("OFF")
            self._runscreen.gripperCamera.setText("OFF")
            self._runscreen.forceSensor.setText("ON")
            self._runscreen.pressureSensor.setText("[0,0,0]")
            """"""
        elif(self.planListIndex==3):
            if(self.panel_type=="leeward_mid_panel"):
                subprocess.Popen(['python', self.YC_transport_code, 'leeward_mid_panel'])
            elif(self.panel_type=="leeward_tip_panel"):
                subprocess.Popen(['python', self.YC_transport_code, 'leeward_tip_panel'])
            self.commands_sent=True
            """
            #self.send_thread=threading.Thread(target=self._execute_steps,args=(3,self.last_step,self.placement_target,0))
            #self.send_thread.setDaemon(True)
            #self.send_thread.start()
            #self._send_event.set()"""
    """
            self._execute_step('plan_transport_payload',self.placement_target)
            self._execute_step('move_transport_payload')

            self._runscreen.vacuum.setText("ON")
            self._runscreen.panel.setText("Attached")
            self._runscreen.panelTag.setText("Localized")
            self._runscreen.nestTag.setText("Not Localized")
            self._runscreen.overheadCamera.setText("OFF")
            self._runscreen.gripperCamera.setText("OFF")
            self._runscreen.forceSensor.setText("ON")
            self._runscreen.pressureSensor.setText("[1,1,1]")
            """"""
        elif(self.planListIndex==4):
            if(self.panel_type=="leeward_mid_panel"):
                subprocess.Popen(['python', self.YC_place_code])
            elif(self.panel_type=="leeward_tip_panel"):
                subprocess.Popen(['python', self.YC_place_code2])
            self.commands_sent=True
            """"""
            self._runscreen.vacuum.setText("ON")
            self._runscreen.panel.setText("Attached")
            self._runscreen.panelTag.setText("Localized")
            self._runscreen.nestTag.setText("Not Localized")
            self._runscreen.overheadCamera.setText("OFF")
            self._runscreen.gripperCamera.setText("OFF")
            self._runscreen.forceSensor.setText("OFF")
            self._runscreen.pressureSensor.setText("[1,1,1]")
            """
        



    def _stopPlan(self):
        #self.client.cancel_all_goals()
        #self.process_client.cancel_all_goals()
        
        #g=GUIStepGoal("stop_plan", self.panel_type)
        #self.client_handle=self.client.send_goal(g,feedback_cb=self._feedback_receive)
        self.step_executor._stopPlan()
        self.recover_from_pause=True
        self._runscreen.nextPlan.setDisabled(False)
        self._runscreen.previousPlan.setDisabled(False)
        self._runscreen.resetToHome.setDisabled(False)
        self.reset_teleop_button()

    def _previousPlan(self):
        if(self.planListIndex==0):
            self.planListIndex=self._runscreen.planList.count()-1
        else:
            self.planListIndex-=1
        self.reset_teleop_button()
        self._runscreen.planList.item(self.planListIndex).setSelected(True)
       # self.rewound=True
        #self._runscreen.previousPlan.setDisabled(True)
        #g=GUIStepGoal("previous_plan", self.panel_type)
        #self.client_handle=self.client.send_goal(g,feedback_cb=self._feedback_receive,done_cb=self._process_done)
        self.step_executor._previousPlan()
    
    @pyqtSlot()
    def _feedback_receive(self):
        with self._lock:
            messagewindow=VacuumConfirm()
            error_msg=self.step_executor.error
            confirm=QMessageBox.warning(messagewindow, 'Error', 'Operation failed with error:\n'+error_msg,QMessageBox.Ok,QMessageBox.Ok)
            self._runscreen.nextPlan.setDisabled(False)
            self._runscreen.previousPlan.setDisabled(False)
            self._runscreen.resetToHome.setDisabled(False)



    def process_state_set(self,data):
        #if(data.state!="moving"):
        self._runscreen.nextPlan.setDisabled(False)
        self._runscreen.previousPlan.setDisabled(False)
        self._runscreen.resetToHome.setDisabled(False)
        





    def _reset_position(self):
        messagewindow=VacuumConfirm()
        reply = QMessageBox.question(messagewindow, 'Path Verification',
                     'Proceed to Reset Position', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply==QMessageBox.Yes:

            self.planListIndex=0
            #g=GUIStepGoal("reset", self.panel_type)
            #self.client_handle=self.client.send_goal(g,feedback_cb=self._feedback_receive)
            self.reset_teleop_button()
            self.step_executor._nextPlan(None,self.planListIndex)
            self._runscreen.planList.item(self.planListIndex).setSelected(True)
            #subprocess.Popen(['python', self.reset_code])
        else:
            rospy.loginfo("Reset Rejected")   

    def start_shared_control(self):
        if(self.planListIndex+1==self._runscreen.planList.count()):
            self.planListIndex=0
        elif self.recover_from_pause:
            self.recover_from_pause=False
        else:
            self.planListIndex+=1

        if(self.planListIndex==1):
            self._execute_step('plan_pickup_prepare',self.panel_type)
        elif(self.planListIndex==2):
            self._execute_step('plan_pickup_lower')
        elif(self.planListIndex==3):
            self._execute_step('plan_pickup_grab_first_step')
            #TODO: How to handle what happens after threshold exceeded to generate next plan step
        elif(self.planListIndex==4):
            self._execute_step('plan_pickup_raise')
        elif(self.planListIndex==5):
            self._execute_step('plan_transport_payload',self.placement_target)
        #self.set_controller_mode(self.controller_commander.MODE_SHARED_TRAJECTORY, 1, [],[])
        
    def change_teleop_modes(self):
        with self._lock:
            self.current_teleop_mode+=1
            
            try:
                if(self.current_teleop_mode==len(self.teleop_modes)):
                    self.current_teleop_mode=1
                    self.controller_commander.set_controller_mode(self.controller_commander.MODE_HALT,1,[],[])
                elif(self.current_teleop_mode==1):
                    self.reset_teleop_button()
                elif(self.current_teleop_mode==2):
                    self.controller_commander.set_controller_mode(self.controller_commander.MODE_JOINT_TELEOP,1,[],[])
                    
                elif(self.current_teleop_mode==3):
                    self.controller_commander.set_controller_mode(self.controller_commander.MODE_CARTESIAN_TELEOP,1,[],[])
                elif(self.current_teleop_mode==4):
                    self.controller_commander.set_controller_mode(self.controller_commander.MODE_CYLINDRICAL_TELEOP,1,[],[])
                elif(self.current_teleop_mode==5):
                    self.controller_commander.set_controller_mode(self.controller_commander.MODE_SPHERICAL_TELEOP,1,[],[])
                rospy.loginfo("Entering teleop mode:"+self.teleop_modes[self.current_teleop_mode])
                button_string=self.teleop_button_string+self.teleop_modes[self.current_teleop_mode]
                self._runscreen.accessTeleop.setText(button_string)
                
            except Exception as err:
                rospy.loginfo(str(err))
                self.step_executor.error="Controller failed to set teleop mode"
                self.step_executor.error_signal.emit()
                
            
            
            

    def set_controller_mode(self,mode,speed_scalar=1.0,ft_bias=[], ft_threshold=[]):
        req=SetControllerModeRequest()
        req.mode.mode=mode
        req.speed_scalar=speed_scalar
        req.ft_bias=ft_bias
        req.ft_stop_threshold=ft_threshold
        res=self._set_controller_mode(req)
        if (res.error_code.mode != ControllerMode.MODE_SUCCESS): raise Exception("Could not set controller mode")

    def error_recovery_button(self):
        self.current_teleop_mode=0
        self._runscreen.accessTeleop.setText("Recover from Error")

    def reset_teleop_button(self):
        self.current_teleop_mode=1
        self.controller_commander.set_controller_mode(self.controller_commander.MODE_HALT,1,[],[])
        button_string=self.teleop_button_string+self.teleop_modes[self.current_teleop_mode]
        self._runscreen.accessTeleop.setText(button_string)


    def callback(self,data):
        #self._widget.State_info.append(data.mode)
        with self._lock:
            if(self.stackedWidget.currentIndex()==2):
                if(self.count>10):
                #stringdata=str(data.mode)
                #freeBytes.acquire()
                #####consoleData.append(str(data.mode))
                    self._errordiagnosticscreen.consoleWidget_2.addItem(str(data.joint_position))
                    self.count=0

                    #print data.joint_position

                self.count+=1
                #self._widget.State_info.scrollToBottom()
                #usedBytes.release()
                #self._data_array.append(stringdata)
                #print self._widget.State_info.count()
                if(self._errordiagnosticscreen.consoleWidget_2.count()>200):

                    item=self._errordiagnosticscreen.consoleWidget_2.takeItem(0)
                    #print "Hello Im maxed out"
                    del item

            '''
            if self.in_process:
                if self.client.get_state() == actionlib.GoalStatus.PENDING or self.client.get_state() == actionlib.GoalStatus.ACTIVE:
                    self._runscreen.nextPlan.setDisabled(True)
                    self._runscreen.previousPlan.setDisabled(True)
                    self._runscreen.resetToHome.setDisabled(True)
                    rospy.loginfo("Pending")
                elif self.client.get_state() == actionlib.GoalStatus.SUCCEEDED:
                    self._runscreen.nextPlan.setDisabled(False)
                    self._runscreen.previousPlan.setDisabled(False)
                    self._runscreen.resetToHome.setDisabled(False)
                    self.in_process=False
                    rospy.loginfo("Succeeded")
                elif self.client.get_state() == actionlib.GoalStatus.ABORTED:
                    self.in_process=False
                    if(not self.recover_from_pause):
                        raise Exception("Process step failed and aborted")

                elif self.client.get_state() == actionlib.GoalStatus.REJECTED:
                    self.in_process=False
                    raise Exception("Process step failed and Rejected")
                elif self.client.get_state() == actionlib.GoalStatus.LOST:
                    self.in_process=False
                    raise Exception("Process step failed and lost")
            '''
            if(self.count>10):
                self.count=0

                if(data.mode.mode<0):
                    '''
                    #self.stackedWidget.setCurrentIndex(2)
                    if(data.mode.mode==-5 or data.mode.mode==-6):
                        error_msg="Error mode %d : Controller is not synched or is in Invalid State" %data.mode.mode
                        self._errordiagnosticscreen.errorLog.setPlainText(error_msg)
                    if(data.mode.mode==-3 or data.mode.mode==-2):
                        error_msg="Error mode %d : Controller operation or argument is invalid" %data.mode.mode
                        self._errordiagnosticscreen.errorLog.setPlainText(error_msg)

                    if(data.mode.mode==-13 or data.mode.mode==-14):
                        error_msg="Error mode %d : Sensor fault or communication Error" %data.mode.mode
                        self._errordiagnosticscreen.errorLog.setPlainText(error_msg)
                    if(data.mode.mode==-1):
                        self._errordiagnosticscreen.errorLog.setPlainText("Error mode -1: Internal system error detected")
                    if(data.mode.mode==-4):
                        self._errordiagnosticscreen.errorLog.setPlainText("Error mode -4: Robot Fault detected")
                    if(data.mode.mode==-7):
                        self._errordiagnosticscreen.errorLog.setPlainText("Error mode -7: Robot singularity detected, controller cannot perform movement")
                    if(data.mode.mode==-8):
                        self._errordiagnosticscreen.errorLog.setPlainText("Error mode -8: Robot Setpoint could not be tracked, robot location uncertain")
                    if(data.mode.mode==-9):
                        self._errordiagnosticscreen.errorLog.setPlainText("Error mode -9: Commanded Trajectory is invalid and cannot be executed. Please replan")
                    if(data.mode.mode==-10):
                        self._errordiagnosticscreen.errorLog.setPlainText("Error mode -10: Trajectory Tracking Error detected, robot position uncertain, consider lowering speed of operation to improve tracking")
                    if(data.mode.mode==-11):
                        self._errordiagnosticscreen.errorLog.setPlainText("Error mode -11: Robot trajectory aborted.")
                    if(data.mode.mode==-12):
                        self._errordiagnosticscreen.errorLog.setPlainText("Error mode -12: Robot Collision Imminent, operation stopped to prevent damage")
                    if(data.mode.mode==-15):
                        self._errordiagnosticscreen.errorLog.setPlainText("Error mode -15: Sensor state is invalid")
                    if(data.mode.mode==-16):
                        self._errordiagnosticscreen.errorLog.setPlainText("Error mode -16: Force Torque Threshold Violation detected, stopping motion to prevent potential collisions/damage")
                    if(data.mode.mode==-17):
                        self._errordiagnosticscreen.errorLog.setPlainText("Error mode -17: Invalid External Setpoint given")
                    '''
                    #messagewindow=VacuumConfirm()
                    #reply = QMessageBox.question(messagewindow, 'Connection Lost',
                             #    'Robot Connection Lost, Return to Welcome Screen?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                    #if reply==QMessageBox.Yes:
                     #
                     #   self.disconnectreturnoption=False
                    #else:
           #             self.disconnectreturnoption=True

                    self.led_change(self.robotconnectionled,False)
                    self.led_change(self.runscreenstatusled,False)
                    self.error_recovery_button()
                else:
                    self.led_change(self.robotconnectionled,True)
                    self.led_change(self.runscreenstatusled,True)
                if(data.ft_wrench_valid=="False"):
                    self.stackedWidget.setCurrentIndex(0)

                    self.led_change(self.forcetorqueled,False)
                else:

                    self.led_change(self.forcetorqueled,True)
                #self.service_list=rosservice.get_service_list()
                


                #if(self.disconnectreturnoption and data.error_msg==""):
                 #   self.disconnectreturnoption=False
            self.count+=1

            if(not self.force_torque_plot_widget.isHidden()):
                self.x_data=np.concatenate((self.x_data,[data.header.seq]))
                incoming=np.array([data.ft_wrench.torque.x,data.ft_wrench.torque.y,data.ft_wrench.torque.z,data.ft_wrench.force.x,data.ft_wrench.force.y,data.ft_wrench.force.z]).reshape(6,1)
                self.force_torque_data=np.concatenate((self.force_torque_data,incoming),axis=1)

                if(self.data_count>500):
                    self.force_torque_data=self.force_torque_data[...,1:]
                    self.x_data=self.x_data[1:]
                    self.force_torque_plot_widget.setRange(xRange=(self.x_data[1],self.x_data[-1]))
                else:
                    self.data_count+=1
                for i in range(6):
                    self.plot_container[i].setData(self.x_data,self.force_torque_data[i,...])
                self.force_torque_app.processEvents()

            if(not self.joint_angle_plot_widget.isHidden()):
                self.x_data=np.concatenate((self.x_data,[data.header.seq]))
                incoming=np.array([data.ft_wrench.torque.x,data.ft_wrench.torque.y,data.ft_wrench.torque.z,data.ft_wrench.force.x,data.ft_wrench.force.y,data.ft_wrench.force.z]).reshape(7,1)
                self.joint_angle_data=np.concatenate((self.joint_angle_data,incoming),axis=1)

                if(self.data_count>500):
                    self.joint_angle_data=self.joint_angle_data[...,1:]
                    self.x_data=self.x_data[1:]
                    self.joint_angle_plot_widget.setRange(xRange=(self.x_data[1],self.x_data[-1]))
                else:
                    self.data_count+=1
                for i in range(7):
                    self.plot_container[i].setData(self.x_data,self.joint_angle_data[i,...])
                self.joint_angle_app.processEvents()
                #if(len(self._data_array)>10):
            #	for x in self._data_array:
            #		self._widget.State_info.append(x)



    def shutdown_plugin(self):
        # TODO unregister all publishers here
        pass

    def save_settings(self, plugin_settings, instance_settings):
        # TODO save intrinsic configuration, usually using:
        # instance_settings.set_value(k, v)
        pass

    def restore_settings(self, plugin_settings, instance_settings):
        # TODO restore intrinsic configuration, usually using:
        # v = instance_settings.value(k)
        pass

    #def trigger_configuration(self):
        # Comment in to signal that the plugin has a way to configure
        # This will enable a setting button (gear icon) in each dock widget title bar
# Usually used to open a modal configuration dialog
