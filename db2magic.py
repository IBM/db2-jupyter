#
# Set up Jupyter MAGIC commands "sql". 
# %sql will return results from a DB2 select statement or execute a DB2 command
#
# IBM 2021: George Baklarz
# Version 2021-11-26
#

from __future__ import print_function
import multiprocessing
from IPython.display import HTML as pHTML, Image as pImage, display as pdisplay, Javascript as Javascript
from IPython.core.magic import (Magics, magics_class, line_magic,
								cell_magic, line_cell_magic, needs_local_scope)
import ibm_db
import pandas
import ibm_db_dbi
import json
import getpass
import pickle
import time
import re
import warnings
import matplotlib
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

_settings = {
	 "maxrows"  : 10,
	 "maxgrid"  : 5,
	 "display"  : "PANDAS",
	 "threads"  : 0,
	 "database" : "",
	 "hostname" : "localhost",
	 "port"     : "50000",
	 "protocol" : "TCPIP",    
	 "uid"      : "DB2INST1",
	 "pwd"      : "password",
	 "ssl"      : "",
	 "passthru" : ""
}

_environment = {
	 "jupyter"  : True,
	 "qgrid"    : True
}

_display = {
	'fullWidthRows': True,
	'syncColumnCellResize': True,
	'forceFitColumns': False,
	'defaultColumnWidth': 150,
	'rowHeight': 28,
	'enableColumnReorder': False,
	'enableTextSelectionOnCells': True,
	'editable': False,
	'autoEdit': False,
	'explicitInitialization': True,
	'maxVisibleRows': 5,
	'minVisibleRows': 5,
	'sortable': True,
	'filterable': False,
	'highlightSelectedCell': False,
	'highlightSelectedRow': True
}

# Db2 and Pandas data types


_db2types = ["unknown",
			 "string",
			 "smallint",
			 "int",
			 "bigint",
			 "real",
			 "float",
			 "decfloat16",
			 "decfloat34",
			 "decimal",
			 "boolean",
			 "clob",
			 "blob",
			 "xml",
			 "date",
			 "time",
			 "timestamp"]

_pdtypes =  ["object",
			 "string",
			 "Int16",
			 "Int32",
			 "Int64",
			 "float32",
			 "float64",
			 "float64",
			 "float64",
			 "float64",
			 "boolean", 
			 "string", 
			 "object",
			 "string",
			 "string",
			 "string",
			 "datetime64"] 

# Connection settings for statements 

_connected = False
_hdbc = None
_hdbi = None
_stmt = []
_stmtID = []
_stmtSQL = []
_vars = {}
_macros = {}
_flags = []
_debug = False

# Db2 Error Messages and Codes
sqlcode = 0
sqlstate = "0"
sqlerror = ""
sqlelapsed = 0

# Check to see if QGrid is installed

try:
	import qgrid
	qgrid.set_defaults(grid_options=_display)
except:
	_environment['qgrid'] = False

if (_environment['qgrid'] == False):
	print("Warning: QGRID is unavailable for displaying results in scrollable windows.")
	print("         Install QGRID if you want to enable scrolling of result sets.")

# Check if we are running in iPython or Jupyter

try:
	if (get_ipython().config == {}): 
		_environment['jupyter'] = False
		_environment['qgrid'] = False
	else:
		_environment['jupyter'] = True
except:
	_environment['jupyter'] = False
	_environment['qgrid'] = False
	
# Check if pandas supports data types in the data frame - Introduced in 1.3 of pandas

_pandas_dtype = False
try:
	_vrm = pandas.__version__.split(".")
	_version  = 0
	_release  = 0
	_modlevel = 0
	if (len(_vrm) >= 1):
		_version  = int(_vrm[0])
	if (len(_vrm) >= 2):
		_release  = int(_vrm[1])
	if (len(_vrm) >= 3):
		_modlevel = int(_vrm[2])
	if (_version >= 1 and _release >= 3):
		_pandas_dtype = True
	else:
		_pandas_dtype = False
except:
	_pandas_dtype = False

if (_pandas_dtype == False):
	print("Warning: PANDAS level does not support Db2 typing which will can increase memory usage.")
	print("         Install PANDAS version 1.3+ for more efficient dataframe creation.")
	
# Check if we have parallism available

_parallel = False
try:
	import multiprocessing as mp
	from multiprocessing.sharedctypes import Value, Array
	_parallel = True
except:
	_parallel = False
	
if (_parallel == False):
	print("Warning: Parallelism is unavailable and THREADS option will be ignored.")
	print("         Install MULTIPROCESSING if you want allow multiple SQL threads to run in parallel.")  
	_settings["threads"] = 0

#
# Set Options for the Db2 Magic Commands
#

def setOptions(inSQL):

	global _settings, _display

	cParms = inSQL.split()
	cnt = 0
	
	if (len(cParms) == 1):
		print("(MAXROWS) Maximum number of rows displayed: " + str(_settings.get("maxrows",10)))
		print("(MAXGRID) Maximum grid display size: " + str(_settings.get("maxgrid",5)))
		print("(DISPLAY) Use PANDAS or GRID display format for output: " + _settings.get("display","PANDAS"))  
		print("(THREADS) Maximum number of threads to use when running SQL: " + str(_settings.get("threads",0)))     
		return

	while cnt < len(cParms):
		
		if cParms[cnt][0] == "?":
			print("%sql OPTION MAXROWS n MAXGRID n DISPLAY n THREADS n")
			print("LIST      - List the current option settings")
			print("MAXROWS n - The maximum number of rows displayed when returning results")
			print("MAXGRID n - Maximum size of a scrollable GRID window")
			print("THREADS n - Maximum number of parallel threads to use when running SQL")
			return
		
		if cParms[cnt].upper() == 'MAXROWS':
			
			if cnt+1 < len(cParms):
				try:
					_settings["maxrows"] = int(cParms[cnt+1])
					if (_settings["maxrows"] > 100 or _settings["maxrows"] <= 0):
						_settings["maxrows"] = 100
				except Exception as err:
					errormsg("Invalid MAXROWS value provided.")
					pass
				cnt = cnt + 1
			else:
				errormsg("No maximum rows specified for the MAXROWS option.")
				return
			
		elif cParms[cnt].upper() == 'MAXGRID':
			
			if cnt+1 < len(cParms):
				try:
					maxgrid = int(cParms[cnt+1])
					if (maxgrid <= 5):                      # Minimum window size is 5
						maxgrid = 5
					_display["maxVisibleRows"] =  int(maxgrid)
					try:
						qgrid.set_defaults(grid_options=_display)
						_settings["maxgrid"] = maxgrid
					except:
						_environment['qgrid'] = False
						
				except Exception as err:
					errormsg("Invalid MAXGRID value provided.")
					pass
				cnt = cnt + 1
			else:
				errormsg("No maximum rows specified for the MAXGRID option.")
				return            
			
		elif cParms[cnt].upper() == 'DISPLAY':
			if cnt+1 < len(cParms):
				if (cParms[cnt+1].upper() == 'GRID'):
					_settings["display"] = 'GRID'
				elif (cParms[cnt+1].upper()  == 'PANDAS'):
					_settings["display"] = 'PANDAS'
				else:
					errormsg("Invalid DISPLAY value provided.")
				cnt = cnt + 1
			else:
				errormsg("No value provided for the DISPLAY option.")
				return  
			
		elif cParms[cnt].upper() == 'THREADS':
			if cnt+1 < len(cParms):
				try:
					threads = int(cParms[cnt+1])
					if (threads < 0):
						threads = 0
					elif (threads > 12):
						threads = 12
					else:
						pass
					_settings["threads"] = threads
				except Exception as err:
					errormsg("Invalid THREADS value provided.")
					pass
				cnt = cnt + 1
			else:
				errormsg("No thread count specified for the THREADS option.")
				return
			
		elif (cParms[cnt].upper() == 'LIST'):
			print("(MAXROWS) Maximum number of rows displayed: " + str(_settings.get("maxrows",10)))
			print("(MAXGRID) Maximum grid display size: " + str(_settings.get("maxgrid",5)))
			print("(DISPLAY) Use PANDAS or GRID display format for output: " + _settings.get("display","PANDAS"))
			print("(THREADS) Maximum number of threads to use when running SQL: " + str(_settings.get("threads",0)))
			return
		else:
			cnt = cnt + 1
			
	save_settings()

	print("(MAXROWS) Maximum number of rows displayed: " + str(_settings.get("maxrows",10)))
	print("(MAXGRID) Maximum grid display size: " + str(_settings.get("maxgrid",5)))
	print("(DISPLAY) Use PANDAS or GRID display format for output: " + _settings.get("display","PANDAS"))
	print("(THREADS) Maximum number of threads to use when running SQL: " + str(_settings.get("threads",0)))
	
	return	

#
# Display help (link to documentation)
#

def sqlhelp():
	
	global _environment
	
	print("Db2 Magic Documentation: https://ibm.github.io/db2-jupyter/")
	return
	
# Split port and IP addresses

def split_string(in_port,splitter=":"):
 
	# Split input into an IP address and Port number
	
	global _settings

	checkports = in_port.split(splitter)
	ip = checkports[0]
	if (len(checkports) > 1):
		port = checkports[1]
	else:
		port = None

	return ip, port

# Parse the CONNECT statement and execute if possible 

def parseConnect(inSQL,local_ns):
	
	global _settings, _connected

	_connected = False
	
	cParms = inSQL.split()
	cnt = 0
	
	_settings["ssl"] = ""
	
	while cnt < len(cParms):
		if cParms[cnt].upper() == 'TO':
			if cnt+1 < len(cParms):
				_settings["database"] = cParms[cnt+1].upper()
				cnt = cnt + 1
			else:
				errormsg("No database specified in the CONNECT statement")
				return
		elif cParms[cnt].upper() == "SSL":
			if cnt+1 < len(cParms):
				if (cParms[cnt+1].upper() in ("ON","TRUE")):
					_settings["ssl"] = "SECURITY=SSL;"
				elif (cParms[cnt+1].upper() in ("OFF","FALSE")):
					_settings["ssl"] = ""
				elif (cParms[cnt+1] != ""):
					cert = cParms[cnt+1]
					_settings["ssl"] = "Security=SSL;SSLServerCertificate={cert};"
				cnt = cnt + 1
			else:
				errormsg("No setting provided for the SSL option (ON | OFF | TRUE | FALSE | certifcate)")
				return
		elif cParms[cnt].upper() == 'CREDENTIALS':
			if cnt+1 < len(cParms):
				credentials = cParms[cnt+1]
				if (credentials in local_ns):
					tempid = eval(credentials,local_ns)
					if (isinstance(tempid,dict) == False): 
						errormsg("The CREDENTIALS variable (" + credentials + ") does not contain a valid Python dictionary (JSON object)")
						return
				else:
					tempid = None
					
				if (tempid == None):
					fname = credentials + ".pickle"
					try:
						with open(fname,'rb') as f: 
							_id = pickle.load(f) 
					except:
						errormsg("Unable to find credential variable or file.")
						return
				else:
					_id = tempid
					
				try:
					_settings["database"] = _id.get("db","")
					_settings["hostname"] = _id.get("hostname","")
					_settings["port"] = _id.get("port","50000")
					_settings["uid"] = _id.get("username","")
					_settings["pwd"] = _id.get("password","")
					try:
						fname = credentials + ".pickle"
						with open(fname,'wb') as f:
							pickle.dump(_id,f)
			
					except:
						errormsg("Failed trying to write Db2 Credentials.")
						return
				except:
					errormsg("Credentials file is missing information. db/hostname/port/username/password required.")
					return
					 
			else:
				errormsg("No Credentials name supplied")
				return
			
			cnt = cnt + 1
			  
		elif cParms[cnt].upper() == 'USER':
			if cnt+1 < len(cParms):
				_settings["uid"] = cParms[cnt+1]
				cnt = cnt + 1
			else:
				errormsg("No userid specified in the CONNECT statement")
				return
		elif cParms[cnt].upper() == 'USING':
			if cnt+1 < len(cParms):
				_settings["pwd"] = cParms[cnt+1]   
				if (_settings.get("pwd","?") == '?'):
					_settings["pwd"] = getpass.getpass("Password [password]: ") or "password"
				cnt = cnt + 1
			else:
				errormsg("No password specified in the CONNECT statement")
				return
		elif cParms[cnt].upper() == 'HOST':
			if cnt+1 < len(cParms):
				hostport = cParms[cnt+1]
				ip, port = split_string(hostport)
				if (port == None): _settings["port"] = "50000"
				_settings["hostname"] = ip
				cnt = cnt + 1
			else:
				errormsg("No hostname specified in the CONNECT statement")
				return
		elif cParms[cnt].upper() == 'PORT':                           
			if cnt+1 < len(cParms):
				_settings["port"] = cParms[cnt+1]
				cnt = cnt + 1
			else:
				errormsg("No port specified in the CONNECT statement")
				return
		elif cParms[cnt].upper() == 'PASSTHRU':                           
			if cnt+1 < len(cParms):
				_settings["passthru"] = cParms[cnt+1]
				cnt = cnt + 1
			else:
				errormsg("No passthru parameters specified in the CONNECT statement")
				return				
		elif cParms[cnt].upper() in ('CLOSE','RESET') :
			try:
				result = ibm_db.close(_hdbc)
				_hdbi.close()
			except:
				pass
			success("Connection closed.")          
			if cParms[cnt].upper() == 'RESET': 
				_settings["database"] = ''
			return
		else:
			cnt = cnt + 1
					 
	_ = db2_doConnect()

def db2_doConnect():
	
	global _hdbc, _hdbi, _connected
	global _settings  

	if _connected == False: 
		
		if len(_settings.get("database","")) == 0:
			return False

	dsn = (
		   "DRIVER={{IBM DB2 ODBC DRIVER}};"
		   "DATABASE={0};"
		   "HOSTNAME={1};"
		   "PORT={2};"
		   "PROTOCOL=TCPIP;ConnectTimeout=15;"
		   "UID={3};"
		   "PWD={4};{5};{6}").format(_settings.get("database",""), 
								 _settings.get("hostname",""), 
								 _settings.get("port","50000"), 
								 _settings.get("uid",""), 
								 _settings.get("pwd",""),
								 _settings.get("ssl",""),
								 _settings.get("passthru",""))

	# Get a database handle (hdbc) and a statement handle (hstmt) for subsequent access to DB2

	try:
		_hdbc  = ibm_db.connect(dsn, "", "")
	except Exception as err:
		db2_error(False,True) # errormsg(str(err))
		_connected = False
		_settings["database"] = ''
		return False
	
	try:
		_hdbi = ibm_db_dbi.Connection(_hdbc)
	except Exception as err:
		db2_error(False,True) # errormsg(str(err))
		_connected = False
		_settings["database"] = ''
		return False  
	
	_connected = True
	
	# Save the values for future use
	
	save_settings()
	
	success("Connection successful.")
	return True
	

def load_settings():

	# This routine will load the settings from the previous session if they exist
	
	global _settings
	
	fname = "db2connect.pickle"

	try:
		with open(fname,'rb') as f: 
			_settings = pickle.load(f) 
				
		_settings["maxgrid"] = 5
		
	except: 
		pass
	
	return

def save_settings():

	# This routine will save the current settings if they exist
	
	global _settings
	
	fname = "db2connect.pickle"
	
	try:
		with open(fname,'wb') as f:
			pickle.dump(_settings,f)
			
	except:
		errormsg("Failed trying to write Db2 Configuration Information.")
 
	return  

def db2_error(quiet,connect=False):
	
	global sqlerror, sqlcode, sqlstate, _environment
	
	try:
		if (connect == False):
			errmsg = ibm_db.stmt_errormsg().replace('\r',' ')
			errmsg = errmsg[errmsg.rfind("]")+1:].strip()
		else:
			errmsg = ibm_db.conn_errormsg().replace('\r',' ')
			errmsg = errmsg[errmsg.rfind("]")+1:].strip()
			
		sqlerror = errmsg
 
		msg_start = errmsg.find("SQLSTATE=")
		if (msg_start != -1):
			msg_end = errmsg.find(" ",msg_start)
			if (msg_end == -1):
				msg_end = len(errmsg)
			sqlstate = errmsg[msg_start+9:msg_end]
		else:
			sqlstate = "0"
	
		msg_start = errmsg.find("SQLCODE=")
		if (msg_start != -1):
			msg_end = errmsg.find(" ",msg_start)
			if (msg_end == -1):
				msg_end = len(errmsg)
			sqlcode = errmsg[msg_start+8:msg_end]
			try:
				sqlcode = int(sqlcode)
			except:
				pass
		else:        
			sqlcode = 0
			
	except:
		errmsg = "Unknown error."
		sqlcode = -99999
		sqlstate = "-99999"
		sqlerror = errmsg
		return
		
	
	msg_start = errmsg.find("SQLSTATE=")
	if (msg_start != -1):
		msg_end = errmsg.find(" ",msg_start)
		if (msg_end == -1):
			msg_end = len(errmsg)
		sqlstate = errmsg[msg_start+9:msg_end]
	else:
		sqlstate = "0"
		
	
	msg_start = errmsg.find("SQLCODE=")
	if (msg_start != -1):
		msg_end = errmsg.find(" ",msg_start)
		if (msg_end == -1):
			msg_end = len(errmsg)
		sqlcode = errmsg[msg_start+8:msg_end]
		try:
			sqlcode = int(sqlcode)
		except:
			pass
	else:
		sqlcode = 0
	
	if quiet == True: return
	
	if (errmsg == ""): return

	html = '<p><p style="border:2px; border-style:solid; border-color:#FF0000; background-color:#ffe6e6; padding: 1em;">'
	
	if (_environment["jupyter"] == True):
		pdisplay(pHTML(html+errmsg+"</p>"))
	else:
		print(errmsg)
	
# Print out an error message

def errormsg(message):
	
	global _environment
	
	if (message != ""):
		html = '<p><p style="border:2px; border-style:solid; border-color:#FF0000; background-color:#ffe6e6; padding: 1em;">'
		if (_environment["jupyter"] == True):
			pdisplay(pHTML(html + message + "</p>"))     
		else:
			print(message)
	
def success(message):
	
	if (message not in (None,"")):
		print(message)
	return   

def debug(message,error=False):
	
	global _environment
	
	if (message in (None,"")):
		return
	
	if (_environment["jupyter"] == True):
		spacer = "<br>" + "&nbsp;"
	else:
		spacer = "\n "
	
	lines = message.split('\n')
	msg = ""
	indent = 0
	for line in lines:
		delta = line.count("(") - line.count(")")
		if (msg == ""):
			msg = line
			indent = indent + delta
		else:
			if (delta < 0): indent = indent + delta
			msg = msg + spacer * (indent*2) + line
			if (delta > 0): indent = indent + delta    

		if (indent < 0): indent = 0
	if (error == True):        
		html = '<p><pre style="font-family: monospace; border:2px; border-style:solid; border-color:#FF0000; background-color:#ffe6e6; padding: 1em;">'                  
	else:
		html = '<p><pre style="font-family: monospace; border:2px; border-style:solid; border-color:#008000; background-color:#e6ffe6; padding: 1em;">'

	if (_environment["jupyter"] == True):
		pdisplay(pHTML(html + msg + "</pre></p>"))
	else:
		print(msg)
		
	return 

def setMacro(inSQL,parms):
	  
	global _macros
	
	names = parms.split()
	if (len(names) < 2):
		errormsg("No command name supplied.")
		return None
	
	macroName = names[1].upper()
	_macros[macroName] = inSQL # inSQL.replace("\t"," ")

	return

def checkMacro(in_sql):
	   
	global _macros
	
	if (len(in_sql) == 0): return(in_sql)          # Nothing to do 
	
	tokens = parseArgs(in_sql,None)                # Take the string and reduce into tokens
	
	macro_name = tokens[0].upper()                 # Uppercase the name of the token
 
	if (macro_name not in _macros): 
		return(in_sql) # No macro by this name so just return the string

	result = runMacro(_macros[macro_name],in_sql,tokens)  # Execute the macro using the tokens we found

	return(result)                                 # Runmacro will either return the original SQL or the new one

def splitassign(arg):
	
	var_name = "null"
	var_value = "null"
	
	arg = arg.strip()
	eq = arg.find("=")
	if (eq != -1):
		var_name = arg[:eq].strip()
		temp_value = arg[eq+1:].strip()
		if (temp_value != ""):
			ch = temp_value[0]
			if (ch in ["'",'"']):
				if (temp_value[-1:] == ch):
					var_value = temp_value[1:-1]
				else:
					var_value = temp_value
			else:
				var_value = temp_value
	else:
		var_value = arg

	return var_name, var_value

def parseArgs(argin,_vars):

	quoteChar = ""
	blockChar = ""
	inQuote = False
	inBlock = False
	inArg = True
	args = []
	arg = ''

	for ch in argin.lstrip():
		if (inBlock == True):
			if (ch == ")"):
				inBlock = False
				arg = arg + ch
			else:
				arg = arg + ch
		elif (inQuote == True):
			if (ch == quoteChar):
				inQuote = False   
				arg = arg + ch #z
			else:
				arg = arg + ch
		elif (ch == "("): # Do we have a block
			arg = arg + ch
			inBlock = True
		elif (ch == "\"" or ch == "\'"): # Do we have a quote
			quoteChar = ch
			arg = arg + ch #z
			inQuote = True
		elif (ch == " "):
			if (arg != ""):
				arg = subvars(arg,_vars)
				args.append(arg)
			else:
				args.append("null")
			arg = ""
		else:
			arg = arg + ch

	if (arg != ""):
		arg = subvars(arg,_vars)
		args.append(arg)   

	return(args)

def runMacro(script,in_sql,tokens):

	result = ""
	runIT = True 
	code = script.split("\n")
	level = 0
	runlevel = [True,False,False,False,False,False,False,False,False,False]
	ifcount = 0
	flags = ""
	_vars = {}

	for i in range(0,len(tokens)):
		vstr = str(i)
		_vars[vstr] = tokens[i]

	if (len(tokens) == 0):
		_vars["argc"] = "0"
	else:
		_vars["argc"] = str(len(tokens)-1)

	for line in code:
		line = line.strip()
		if (line == "" or line == "\n"): continue
		if (line[0] == "#"): continue    # A comment line starts with a # in the first position of the line
		args = parseArgs(line,_vars)     # Get all of the arguments
		if (args[0] == "if"):
			ifcount = ifcount + 1
			if (runlevel[level] == False): # You can't execute this statement
				continue
			level = level + 1    
			if (len(args) < 4):
				print("Macro: Incorrect number of arguments for the if clause.")
				return in_sql
			arg1 = args[1]
			arg2 = args[3]
			if (len(arg2) > 2):
				ch1 = arg2[0]
				ch2 = arg2[-1:]
				if (ch1 in ['"',"'"] and ch1 == ch2):
					arg2 = arg2[1:-1].strip()

			op   = args[2]
			if (op in ["=","=="]):
				if (arg1 == arg2):
					runlevel[level] = True
				else:
					runlevel[level] = False                
			elif (op in ["<=","=<"]):
				if (arg1 <= arg2):
					runlevel[level] = True
				else:
					runlevel[level] = False                
			elif (op in [">=","=>"]):                    
				if (arg1 >= arg2):
					runlevel[level] = True
				else:
					runlevel[level] = False                                       
			elif (op in ["<>","!="]):                    
				if (arg1 != arg2):
					runlevel[level] = True
				else:
					runlevel[level] = False  
			elif (op in ["<"]):
				if (arg1 < arg2):
					runlevel[level] = True
				else:
					runlevel[level] = False                
			elif (op in [">"]):
				if (arg1 > arg2):
					runlevel[level] = True
				else:
					runlevel[level] = False                
			else:
				print("Macro: Unknown comparison operator in the if statement:" + op)

				continue

		elif (args[0] in ["exit","echo"] and runlevel[level] == True):
			msg = ""
			for msgline in args[1:]:
				if (msg == ""):
					msg = subvars(msgline,_vars)
				else:
					msg = msg + " " + subvars(msgline,_vars)
			if (msg != ""): 
				if (args[0] == "echo"):
					debug(msg,error=False)
				else:
					debug(msg,error=True)
			if (args[0] == "exit"): return ''

		elif (args[0] == "pass" and runlevel[level] == True):
			pass

		elif (args[0] == "flags" and runlevel[level] == True):
			if (len(args) > 1):
				for i in range(1,len(args)):
					flags = flags + " " + args[i]
				flags = flags.strip()

		elif (args[0] == "var" and runlevel[level] == True):
			value = ""
			for val in args[2:]:
				if (value == ""):
					value = subvars(val,_vars)
				else:
					value = value + " " + subvars(val,_vars)
			value.strip()
			_vars[args[1]] = value 

		elif (args[0] == 'else'):

			if (ifcount == level):
				runlevel[level] = not runlevel[level]

		elif (args[0] == 'return' and runlevel[level] == True):
			return(f"{flags} {result}")

		elif (args[0] == "endif"):
			ifcount = ifcount - 1
			if (ifcount < level):
				level = level - 1
				if (level < 0):
					print("Macro: Unmatched if/endif pairs.")
					return ''

		else:
			if (runlevel[level] == True):
				if (result == ""):
					result = subvars(line,_vars)
				else:
					result = result + "\n" + subvars(line,_vars)

	return(f"{flags} {result}")      

def subvars(script,_vars):
	
	if (_vars == None): return script
	
	remainder = script
	result = ""
	done = False
	
	while done == False:
		bv = remainder.find("{")
		if (bv == -1):
			done = True
			continue
		ev = remainder.find("}")
		if (ev == -1):
			done = True
			continue
		result = result + remainder[:bv]
		vvar = remainder[bv+1:ev].strip()
		remainder = remainder[ev+1:]
		
		modifier = ""
		
		if (len(vvar) == 0):
			errormsg(f"No variable name supplied in the braces {{}}")
			return script
		
		upper = False
		allvars = False
		concat = " "
		
		if (len(vvar) > 1):
			modifier = vvar[0]
			if (modifier == "^"):
				upper = True
				vvar = vvar[1:]
			elif (modifier == "*"):
				vvar = vvar[1:]
				allvars = True
				concat = " "
			elif (vvar[0] == ","):
				vvar = vvar[1:]
				allvars = True
				concat = ","
			else:
				pass
		
		if (vvar in _vars):
			if (upper == True):
				items = _vars[vvar].upper()
			elif (allvars == True):
				try:
					iVar = int(vvar)
				except:
					return(script)
				items = ""
				sVar = str(iVar)
				while sVar in _vars:
					if (items == ""):
						items = _vars[sVar]
					else:
						items = items + concat + _vars[sVar]
					iVar = iVar + 1
					sVar = str(iVar)
			else:
				items = _vars[vvar]
		else:
			if (allvars == True):
				items = ""
			else:
				items = "null"                
				 
		result = result + items
				
	if (remainder != ""):
		result = result + remainder
		
	return(result)

def splitargs(arguments):
	
	import types
	
	# String the string and remove the ( and ) characters if they at the beginning and end of the string
	
	results = []
	
	step1 = arguments.strip()
	if (len(step1) == 0): return(results)       # Not much to do here - no args found
	
	if (step1[0] == '('):
		if (step1[-1:] == ')'):
			step2 = step1[1:-1]
			step2 = step2.strip()
		else:
			step2 = step1
	else:
		step2 = step1
			
	# Now we have a string without brackets. Start scanning for commas
			
	quoteCH = ""
	pos = 0
	arg = ""
	args = []
			
	while pos < len(step2):
		ch = step2[pos]
		if (quoteCH == ""):                     # Are we in a quote?
			if (ch in ('"',"'")):               # Check to see if we are starting a quote
				quoteCH = ch
				arg = arg + ch
				pos += 1
			elif (ch == ","):                   # Are we at the end of a parameter?
				arg = arg.strip()
				args.append(arg)
				arg = ""
				inarg = False 
				pos += 1
			else:                               # Continue collecting the string
				arg = arg + ch
				pos += 1
		else:
			if (ch == quoteCH):                 # Are we at the end of a quote?
				arg = arg + ch                  # Add the quote to the string
				pos += 1                        # Increment past the quote
				quoteCH = ""                    # Stop quote checking (maybe!)
			else:
				pos += 1
				arg = arg + ch

	if (quoteCH != ""):                         # So we didn't end our string
		arg = arg.strip()
		args.append(arg)
	elif (arg != ""):                           # Something left over as an argument
		arg = arg.strip()
		args.append(arg)
	else:
		pass
	
	results = []
	
	for arg in args:
		result = []
		if (len(arg) > 0):
			if (arg[0] in ('"',"'")):
				value = arg[1:-1]
				isString = True
				isNumber = False
			else:
				isString = False 
				isNumber = False 
				try:
					value = eval(arg)
					if (type(value) == int):
						isNumber = True
					elif (isinstance(value,float) == True):
						isNumber = True
					else:
						value = arg
				except:
					value = arg

		else:
			value = ""
			isString = False
			isNumber = False
			
		result = [value,isString,isNumber]
		results.append(result)
		
	return results

def createDF(hdbc,hdbi,sqlin,local_ns):
	
	import datetime
	import ibm_db    
	
	global sqlcode, _settings, _parallel
	
	NoDF  = False
	YesDF = True
	
	if (hdbc == None or hdbi == None):
		errormsg("You need to connect to a database before issuing this command.")
		return NoDF, None
	
	# Strip apart the command into tokens based on spaces
	tokens = sqlin.split()
	
	token_count = len(tokens)
	
	if (token_count < 5): # Not enough parameters
		errormsg("Insufficient arguments for USING command")
		return NoDF, None
		
	keyword_command = tokens[0].upper()
	dfName          = tokens[1]
	keyword_create  = tokens[2].upper()
	keyword_table   = tokens[3].upper()
	table           = tokens[4]           
	
	if (dfName not in local_ns):
		errormsg("The variable ({dfName}) does not exist in the local variable list.")
		return NoDF, None    

	try:
		dfValue = eval(dfName,None,local_ns) # globals()[varName] # eval(varName)
	except:
		errormsg("The variable ({dfName}) does not contain a value.")
		return NoDF, None     
   
	if (keyword_create in ("SELECT","WITH")):
		
		if (_parallel == False):
			errormsg("Parallelism is not availble on this system.")
			return NoDF, None
 
		thread_count = _settings.get("threads",0)
		if (thread_count in (0,1)):
			errormsg("The THREADS option is currently set to 0 or 1 which disables parallelism.")
			return NoDF, None      
		
		ok, df = dfSQL(hdbc,hdbi,sqlin,dfName,dfValue,thread_count)
		
		if (ok == False):
			return NoDF, None
		else:
			return YesDF, df
				
	if (isinstance(dfValue,pandas.DataFrame) == False): # Not a Pandas dataframe
		errormsg("The variable ({dfName}) is not a Pandas dataframe.")
		return NoDF, None
	
	if (keyword_create not in ("CREATE","REPLACE","APPEND") or keyword_table != "TABLE"):
		errormsg("Incorrect syntax: %sql using <df> create table <name> [options]")
		return NoDF, None
	
	if (token_count % 2 != 1):
		errormsg("Insufficient arguments for USING command.")
		return NoDF, None
		
	flag_withdata = False
	flag_asis     = False
	flag_float    = False
	flag_integer  = False
	limit         = -1
		
	for token_idx in range(5,token_count,2):

		option_key = tokens[token_idx].upper()
		option_val = tokens[token_idx+1].upper()
		if (option_key == "WITH" and option_val == "DATA"):
			flag_withdata = True
		elif (option_key == "COLUMNS" and option_val == "ASIS"):
			flag_asis = True
		elif (option_key == "KEEP" and option_val == "FLOAT64"):
			flag_float = True
		elif (option_key == "KEEP" and option_val == "INT64"):
			flag_integer = True
		elif (option_key == "LIMIT"):
			if (option_val.isnumeric() == False):
				errormsg("The LIMIT must be a valid number from -1 (unlimited) to the maximun number of rows to insert")
				return NoDF, None
			limit = int(option_val)
		else:
			errormsg("Invalid options. Must be either WITH DATA | COLUMNS ASIS | KEEP FLOAT64 | KEEP FLOAT INT64")
			return NoDF, None   

	if (keyword_create == "REPLACE"):
		sql = f"DROP TABLE {table}"
		ok = execSQL(hdbc,sql,quiet=True)   

	sql = [] 
	columns = dict(dfValue.dtypes)
	sql.append(f'CREATE TABLE {table} (')
	datatypes = []
	comma = ""
	for column in columns:
		datatype = str(columns[column])
		datatype = datatype.upper()

		if (datatype == "OBJECT"):
			datapoint = dfValue[column][0]
			if (isinstance(datapoint,datetime.datetime)):
				type = "TIMESTAMP"
			elif (isinstance(datapoint,datetime.time)):
				type = "TIME"
			elif (isinstance(datapoint,datetime.date)):
				type = "DATE"
			elif (isinstance(datapoint,float)):
				if (flag_float == True):
					type = "FLOAT"
				else:
					type = "DECFLOAT"
			elif (isinstance(datapoint,int)):
				if (flag_integer == True):
					type = "BIGINT"
				else:
					type = "INTEGER"
			elif (isinstance(datapoint,str)):
				maxlength = dfValue[column].apply(str).apply(len).max()
				type = f"VARCHAR({maxlength})"
			else:
				type = "CLOB"
		elif (datatype == "INT64"):
			type = "BIGINT"
		elif (datatype == "INT32"):
			type = "INT"
		elif (datatype == "INT16"):
			type = "SMALLINT"
		elif (datatype == "FLOAT64"):
			if (flag_float == True):
				type = "FLOAT"
			else:
				type = "DECFLOAT"
		elif (datatype == "FLOAT32"):
			if (flag_float == True):
				type = "REAL"
			else:
				type = "DECFLOAT"
		elif ("DATETIME64" in datatype):
			type = "TIMESTAMP"
		elif (datatype == "BOOLEAN"):
			type = "BINARY"
		elif (datatype == "STRING"):
			maxlength = dfValue[column].apply(str).apply(len).max()
			type = f"VARCHAR({maxlength})"
		else:
			type = "CLOB"
			
		datatypes.append(type)    

		if (flag_asis == False):
			if (isinstance(column,str) == False):
				column = str(column)
			identifier = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
			column_name = column.strip().upper()
			new_name = ""
			for ch in column_name:
				if (ch not in identifier):
					new_name = new_name + "_"
				else:
					new_name = new_name + ch
					
			new_name = new_name.lstrip('_').rstrip('_')
			
			if (new_name == "" or new_name[0] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
				new_name = f'"{column}"'
		else:
			new_name = f'"{column}"'
		
		sql.append(f"    {new_name} {type}")
	sql.append(")")

	sqlcmd = ""
	for i in range(0,len(sql)):
		if (i > 0 and i < len(sql)-2):
			comma = ","
		else:
			comma = ""
		sqlcmd = "{}\n{}{}".format(sqlcmd,sql[i],comma)
		
	if (keyword_create != "APPEND"):
		print(sqlcmd)
		ok = execSQL(hdbc,sqlcmd,quiet=False)
		if (ok == False):
			return NoDF, None

	if (flag_withdata == True or keyword_create == "APPEND"):
		
		autocommit = ibm_db.autocommit(hdbc)
		ibm_db.autocommit(hdbc,False)

		row_count = 0
		insert_sql = ""
		rows, cols = dfValue.shape
		for row in range(0,rows):
 
			insert_row = ""
			for col in range(0, cols):
				
				value = dfValue.iloc[row][col]
				value = str(value)
				
				if (value.upper() in ("NAN","<NA>","NAT")):
					value = "NULL"
				else:
					addquotes_flag = False
					if (datatypes[col] == "CLOB" or "VARCHAR" in datatypes[col]):
						addquotes_flag = True
					elif (datatypes[col] in ("TIME","DATE","TIMESTAMP")):
						addquotes_flag = True
					elif (datatypes[col] in ("INTEGER","INT","SMALLINT","BIGINT","DECFLOAT","FLOAT","BINARY","REAL")):
						addquotes_flag = False
					else:
						addquotes_flag = True
						
					if (addquotes_flag == True):
						value = addquotes(value,True)
					  
				if (insert_row == ""):
					insert_row = f"{value}"
				else:
					insert_row = f"{insert_row},{value}"
					  
			if (insert_sql == ""):
				insert_sql = f"INSERT INTO {table} VALUES ({insert_row})"
			else:
				insert_sql = f"{insert_sql},({insert_row})"
					  
			row_count += 1
			if (row_count % 1000 == 0 or row_count == limit):
				try:
					result = ibm_db.exec_immediate(hdbc, insert_sql)                 # Run it 
				except:
					db2_error(False)
					return NoDF, None

				ibm_db.commit(hdbc)

				print(f"\r{row_count} of {rows} rows inserted.",end="")
					
				insert_sql = ""
				
			if (row_count == limit):
				break
					  
		if (insert_sql != ""):
			try:
				result = ibm_db.exec_immediate(hdbc, insert_sql)                 # Run it                            
			except:
				db2_error(False)       
				return NoDF, None

			ibm_db.commit(hdbc)

		ibm_db.autocommit(hdbc,autocommit)

		print("\nInsert completed.")
					  
	return NoDF, None

def sqlParser(sqlin,local_ns):
	   
	sql_cmd = ""
	encoded_sql = sqlin
	
	firstCommand = "(?:^\s*)([a-zA-Z]+)(?:\s+.*|$)"
	
	findFirst = re.match(firstCommand,sqlin)
	
	if (findFirst == None): # We did not find a match so we just return the empty string
		return sql_cmd, encoded_sql
	
	cmd = findFirst.group(1)
	sql_cmd = cmd.upper()

	#
	# Scan the input string looking for variables in the format :var. If no : is found just return.
	# Var must be alpha+number+_ to be valid
	#
	
	if (':' not in sqlin): # A quick check to see if parameters are in here, but not fool-proof!         
		return sql_cmd, encoded_sql    
	
	inVar = False 
	inQuote = "" 
	varName = ""
	encoded_sql = ""
	
	STRING = 0
	NUMBER = 1
	LIST = 2
	RAW = 3
	PANDAS = 5
	
	for ch in sqlin:
		if (inVar == True): # We are collecting the name of a variable
			if (ch.upper() in "@_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789[]"):
				varName = varName + ch
				continue
			else:
				if (varName == ""):
					encode_sql = encoded_sql + ":"
				elif (varName[0] in ('[',']')):
					encoded_sql = encoded_sql + ":" + varName
				else:
					if (ch == '.'): # If the variable name is stopped by a period, assume no quotes are used
						flag_quotes = False
					else:
						flag_quotes = True
					varValue, varType = getContents(varName,flag_quotes,local_ns)
					if (varType != PANDAS and varValue == None):                 
						encoded_sql = encoded_sql + ":" + varName
					else:
						if (varType == STRING):
							encoded_sql = encoded_sql + varValue
						elif (varType == NUMBER):
							encoded_sql = encoded_sql + str(varValue)
						elif (varType == RAW):
							encoded_sql = encoded_sql + varValue
						elif (varType == PANDAS):
							insertsql = ""
							coltypes = varValue.dtypes
							rows, cols = varValue.shape
							for row in range(0,rows):
								insertrow = ""
								for col in range(0, cols):
									value = varValue.iloc[row][col]
									if (coltypes[col] == "object"):
										value = str(value)
										value = addquotes(value,True)
									else:
										strvalue = str(value)
										if ("NAN" in strvalue.upper()):
											value = "NULL"    
									if (insertrow == ""):
										insertrow = f"{value}"
									else:
										insertrow = f"{insertrow},{value}"
								if (insertsql == ""):
									insertsql = f"({insertrow})"
								else:
									insertsql = f"{insertsql},({insertrow})"  
							encoded_sql = encoded_sql + insertsql
						elif (varType == LIST):
							start = True
							for v in varValue:
								if (start == False):
									encoded_sql = encoded_sql + ","
								if (isinstance(v,int) == True):         # Integer value 
									encoded_sql = encoded_sql + str(v)
								elif (isinstance(v,float) == True):
									encoded_sql = encoded_sql + str(v)
								else:
									flag_quotes = True
									try:
										if (v.find('0x') == 0):               # Just guessing this is a hex value at beginning
											encoded_sql = encoded_sql + v
										else:
											encoded_sql = encoded_sql + addquotes(v,flag_quotes)      # String
									except:
										encoded_sql = encoded_sql + addquotes(str(v),flag_quotes)                                   
								start = False

				encoded_sql = encoded_sql + ch
				varName = ""
				inVar = False  
		elif (inQuote != ""):
			encoded_sql = encoded_sql + ch
			if (ch == inQuote): inQuote = ""
		elif (ch in ("'",'"')):
			encoded_sql = encoded_sql + ch
			inQuote = ch
		elif (ch == ":"): # This might be a variable
			varName = ""
			inVar = True
		else:
			encoded_sql = encoded_sql + ch
	
	if (inVar == True):
		varValue, varType = getContents(varName,True,local_ns) # We assume the end of a line is quoted
		if (varType != PANDAS and varValue == None):                 
			encoded_sql = encoded_sql + ":" + varName  
		else:
			if (varType == STRING):
				encoded_sql = encoded_sql + varValue
			elif (varType == RAW):
				encoded_sql = encoded_sql + varValue                
			elif (varType == NUMBER):
				encoded_sql = encoded_sql + str(varValue)
			elif (varType == PANDAS):
				insertsql = ""
				coltypes = varValue.dtypes
				rows, cols = varValue.shape
				for row in range(0,rows):
					insertrow = ""
					for col in range(0, cols):
						value = varValue.iloc[row][col]
						if (coltypes[col] == "object"):
							value = str(value)
							value = addquotes(value,True)
						else:
							strvalue = str(value)
							if ("NAN" in strvalue.upper()):
								value = "NULL"    
						if (insertrow == ""):
							insertrow = f"{value}"
						else:
							insertrow = f"{insertrow},{value}"
					if (insertsql == ""):
						insertsql = f"({insertrow})"
					else:
						insertsql = f"{insertsql},({insertrow})"  
				encoded_sql = encoded_sql + insertsql                
			elif (varType == LIST):
				flag_quotes = True
				start = True
				for v in varValue:
					if (start == False):
						encoded_sql = encoded_sql + ","
					if (isinstance(v,int) == True):         # Integer value 
						encoded_sql = encoded_sql + str(v)
					elif (isinstance(v,float) == True):
						encoded_sql = encoded_sql + str(v)
					else:
						try:
							if (v.find('0x') == 0):               # Just guessing this is a hex value
								encoded_sql = encoded_sql + v
							else:
								encoded_sql = encoded_sql + addquotes(v,flag_quotes)              # String
						except:
							encoded_sql = encoded_sql + addquotes(str(v),flag_quotes)                                 
					start = False

	return sql_cmd, encoded_sql

def plotData(hdbi, sql):
	
	try:
		df = pandas.read_sql(sql,hdbi)
		  
	except Exception as err:
		db2_error(False)
		return
				
		
	if df.empty:
		errormsg("No results returned")
		return
	
	col_count = len(df.columns)

	if flag(["-pb","-bar"]):                                    # Plot 1 = bar chart
	
		if (col_count in (1,2,3)):
			
			if (col_count == 1):
 
				df.index = df.index + 1
				_ = df.plot(kind='bar');
				_ = plt.plot();
				
			elif (col_count == 2):
 
				xlabel = df.columns.values[0]
				ylabel = df.columns.values[1]
				df.plot(kind='bar',x=xlabel,y=ylabel);
				_ = plt.plot();
				
			else:
 
				values = df.columns.values[2]
				columns = df.columns.values[0]
				index = df.columns.values[1]
				pivoted = pandas.pivot_table(df, values=values, columns=columns, index=index) 
				_ = pivoted.plot.bar(); 
			
		else:
			errormsg("Can't determine what columns to plot")
			return
					
	elif flag(["-pp","-pie"]):                                  # Plot 2 = pie chart
		
		if (col_count in (1,2)):  
				
			if (col_count == 1):
				df.index = df.index + 1
				yname = df.columns.values[0]
				_ = df.plot(kind='pie',y=yname);                
			else:          
				xlabel = df.columns.values[0]
				xname = df[xlabel].tolist()
				yname = df.columns.values[1]
				_ = df.plot(kind='pie',y=yname,labels=xname);
				
			plt.show();
			
		else:
			errormsg("Can't determine what columns to plot")
			return
					
	elif flag(["-pl","-line"]):                                  # Plot 3 = line chart
			
		if (col_count in (1,2,3)): 
			
			if (col_count == 1):
				df.index = df.index + 1  
				_ = df.plot(kind='line');          
			elif (col_count == 2):            
				xlabel = df.columns.values[0]
				ylabel = df.columns.values[1]
				_ = df.plot(kind='line',x=xlabel,y=ylabel) ; 
			else:         
				values = df.columns.values[2]
				columns = df.columns.values[0]
				index = df.columns.values[1]
				pivoted = pandas.pivot_table(df, values=values, columns=columns, index=index)
				_ = pivoted.plot();
				
			plt.show();
				
		else:
			errormsg("Can't determine what columns to plot")
			return
	else:
		return

def getContents(varName,flag_quotes,local_ns):
	
	#
	# Get the contents of the variable name that is passed to the routine. Only simple
	# variables are checked, i.e. arrays and lists are not parsed
	#
	
	STRING = 0
	NUMBER = 1
	LIST = 2
	RAW = 3
	DICT = 4
	PANDAS = 5
	
	try:
		value = eval(varName,None,local_ns) # globals()[varName] # eval(varName)
	except:
		return(None,STRING)
	
	if (isinstance(value,dict) == True):          # Check to see if this is JSON dictionary
		return(addquotes(value,flag_quotes),STRING)

	elif(isinstance(value,list) == True or isinstance(value,tuple) == True):         # List - tricky 
		return(value,LIST)
	
	elif (isinstance(value,pandas.DataFrame) == True): # Pandas dataframe
		return(value,PANDAS)

	elif (isinstance(value,int) == True):         # Integer value 
		return(value,NUMBER)

	elif (isinstance(value,float) == True):       # Float value
		return(value,NUMBER)

	else:
		try:
			# The pattern needs to be in the first position (0 in Python terms)
			if (value.find('0x') == 0):               # Just guessing this is a hex value
				return(value,RAW)
			else:
				return(addquotes(value,flag_quotes),STRING)                     # String
		except:
			return(addquotes(str(value),flag_quotes),RAW)

def addquotes(inString,flag_quotes):
	
	if (isinstance(inString,dict) == True):          # Check to see if this is JSON dictionary
		serialized = json.dumps(inString) 
	else:
		serialized = inString

	# Replace single quotes with '' (two quotes) and wrap everything in single quotes
	if (flag_quotes == False):
		return(serialized)
	else:
		return("'"+serialized.replace("'","''")+"'")    # Convert single quotes to two single quotes
	
def checkOption(args_in, option, vFalse=False, vTrue=True):
	
	args_out = args_in.strip()
	found = vFalse
	
	if (args_out != ""):
		if (args_out.find(option) >= 0):
			args_out = args_out.replace(option," ")
			args_out = args_out.strip()
			found = vTrue

	return args_out, found

def findProc(procname):
	
	global _hdbc, _hdbi, _connected
	
	# Split the procedure name into schema.procname if appropriate
	upper_procname = procname.upper()
	schema, proc = split_string(upper_procname,".") # Expect schema.procname
	if (proc == None):
		proc = schema

	# Call ibm_db.procedures to see if the procedure does exist
	schema = "%"

	try:
		stmt = ibm_db.procedures(_hdbc, None, schema, proc) 
		if (stmt == False):                         # Error executing the code
			errormsg("Procedure " + procname + " not found in the system catalog.")
			return None

		result = ibm_db.fetch_tuple(stmt)
		resultsets = result[5]
		if (resultsets >= 1): resultsets = 1
		return resultsets
			
	except Exception as err:
		errormsg("Procedure " + procname + " not found in the system catalog.")
		return None

def parseCallArgs(macro):
	
	quoteChar = ""
	inQuote = False
	inParm = False
	ignore = False
	name = ""
	parms = []
	parm = ''
	
	sqlin = macro.replace("\n","")
	sqlin.lstrip()
	
	for ch in sqlin:
		if (inParm == False):
			# We hit a blank in the name, so ignore everything after the procedure name until a ( is found
			if (ch == " "): 
				ignore == True
			elif (ch ==  "("): # Now we have parameters to send to the stored procedure
				inParm = True
			else:
				if (ignore == False): name = name + ch # The name of the procedure (and no blanks)
		else:
			if (inQuote == True):
				if (ch == quoteChar):
					inQuote = False  
				else:
					parm = parm + ch
			elif (ch in ("\"","\'","[")): # Do we have a quote
				if (ch == "["):
					quoteChar = "]"
				else:
					quoteChar = ch
				inQuote = True
			elif (ch == ")"):
				if (parm != ""):
					parms.append(parm)
				parm = ""
				break
			elif (ch == ","):
				if (parm != ""):
					parms.append(parm)                  
				else:
					parms.append("null")
					
				parm = ""

			else:
				parm = parm + ch
				
	if (inParm == True):
		if (parm != ""):
			parms.append(parm)    
					   
	return(name,parms)

def getColumns(stmt):
	   
	columns = []
	types = []
	colcount = 0
	try:
		colname = ibm_db.field_name(stmt,colcount)
		coltype = ibm_db.field_type(stmt,colcount)
		precision = ibm_db.field_precision(stmt,colcount)
		while (colname != False):
			if (coltype == "real"):
				if (precision == 7):
					coltype = "real"
				elif (precision == 15):
					coltype = "float"
				elif (precision == 16):
					coltype = "decfloat16"
				elif (precision == 34):
					coltype = "decfloat34"
				else:
					coltype = "real"
			elif (coltype == "int"):
				if (precision == 1):
					coltype = "boolean"
				elif (precision == 5):
					coltype = "smallint"
				elif (precision == 10):
					coltype = "int"
				else:
					coltype = "int"
			columns.append(colname)
			types.append(coltype)
			colcount += 1
			colname = ibm_db.field_name(stmt,colcount)
			coltype = ibm_db.field_type(stmt,colcount)  
			precision = ibm_db.field_precision(stmt,colcount)     
			
		return columns,types   
				
	except Exception as err:
		db2_error(False)
		return None

def parseCall(hdbc, inSQL, local_ns):
	
	global _hdbc, _hdbi, _connected, _environment
	
	# Check to see if we are connected first
	if (_connected == False):                                      # Check if you are connected 
		db2_doConnect()
		if _connected == False: return None
	 
	remainder = inSQL.strip()
	procName, procArgs = parseCallArgs(remainder[5:]) # Assume that CALL ... is the format
	
	resultsets = findProc(procName)
	if (resultsets == None): return None
	
	argvalues = []
 
	if (len(procArgs) > 0): # We have arguments to consider
		for arg in procArgs:
			varname = arg
			if (len(varname) > 0):
				if (varname[0] == ":"):
					checkvar = varname[1:]
					varvalue = getContents(checkvar,True,local_ns)
					if (varvalue == None):
						errormsg("Variable " + checkvar + " is not defined.")
						return None
					argvalues.append(varvalue)
				else:
					if (varname.upper() == "NULL"):
						argvalues.append(None)
					else:
						argvalues.append(varname)
			else:
				argvalues.append(None)

	
	try:

		if (len(procArgs) > 0):
			argtuple = tuple(argvalues)
			result = ibm_db.callproc(_hdbc,procName,argtuple)
			stmt = result[0]
		else:
			result = ibm_db.callproc(_hdbc,procName)
			stmt = result
		
		if (resultsets != 0 and stmt != None): 

			columns, types = getColumns(stmt)
			if (columns == None): return None
			
			rows = []
			rowlist = ibm_db.fetch_tuple(stmt)
			while ( rowlist ) :
				row = []
				colcount = 0
				for col in rowlist:
					try:
						if (types[colcount] in ["int","bigint"]):
							row.append(int(col))
						elif (types[colcount] in ["decimal","real"]):
							row.append(float(col))
						elif (types[colcount] in ["date","time","timestamp"]):
							row.append(str(col))
						else:
							row.append(col)
					except:
						row.append(col)
					colcount += 1
				rows.append(row)
				rowlist = ibm_db.fetch_tuple(stmt)
			
			if flag(["-r","-array"]):
				rows.insert(0,columns)
				if len(procArgs) > 0:
					allresults = []
					allresults.append(rows)
					for x in result[1:]:
						allresults.append(x)
					return allresults # rows,returned_results
				else:
					return rows
			else:
				df = pandas.DataFrame.from_records(rows,columns=columns)
				if flag("-grid") or _settings.get('display',"PANDAS") == 'GRID':
					if (_environment['qgrid'] == False):
						with pandas.option_context('display.max_rows', None, 'display.max_columns', None):  
							pdisplay(df)
					else:
						try:
							pdisplay(qgrid.show_grid(df))
						except:
							errormsg("Grid cannot be used to display data with duplicate column names. Use option -a or %sql OPTION DISPLAY PANDAS instead.")
							
					return                             
				else:
					if flag(["-a","-all"]) or _settings.get("maxrows",10) == -1 : # All of the rows
						with pandas.option_context('display.max_rows', 100, 'display.max_columns', None): 
							pdisplay(df)
					else:
						return df
			
		else:
			if len(procArgs) > 0:
				allresults = []
				for x in result[1:]:
					allresults.append(x)
				return allresults # rows,returned_results
			else:
				return None
			
	except Exception as err:
		db2_error(False)
		return None

def parsePExec(hdbc, inSQL):
	 
	import ibm_db    
	global _stmt, _stmtID, _stmtSQL, sqlcode
	
	cParms = inSQL.split()
	parmCount = len(cParms)
	if (parmCount == 0): return(None)                          # Nothing to do but this shouldn't happen
	
	keyword = cParms[0].upper()                                  # Upper case the keyword
	
	if (keyword == "PREPARE"):                                   # Prepare the following SQL
		uSQL = inSQL.upper()
		found = uSQL.find("PREPARE")
		sql = inSQL[found+7:].strip()

		try:
			pattern = "\?\*[0-9]+"
			findparm = re.search(pattern,sql)
			while findparm != None:
				found = findparm.group(0)
				count = int(found[2:])
				markers = ('?,' * count)[:-1]
				sql = sql.replace(found,markers)
				findparm = re.search(pattern,sql)
			
			stmt = ibm_db.prepare(hdbc,sql) # Check error code here
			if (stmt == False): 
				db2_error(False)
				return(False)
			
			stmttext = str(stmt).strip()
			stmtID = stmttext[33:48].strip()
			
			if (stmtID in _stmtID) == False:
				_stmt.append(stmt)              # Prepare and return STMT to caller
				_stmtID.append(stmtID)
			else:
				stmtIX = _stmtID.index(stmtID)
				_stmt[stmtIX] = stmt
				 
			return(stmtID)
		
		except Exception as err:
			print(err)
			db2_error(False)
			return(False)

	if (keyword == "EXECUTE"):                                  # Execute the prepare statement
		if (parmCount < 2): return(False)                    # No stmtID available
		
		stmtID = cParms[1].strip()
		if (stmtID in _stmtID) == False:
			errormsg("Prepared statement not found or invalid.")
			return(False)

		stmtIX = _stmtID.index(stmtID)
		stmt = _stmt[stmtIX]

		try:        

			if (parmCount == 2):                           # Only the statement handle available
				result = ibm_db.execute(stmt)               # Run it
			elif (parmCount == 3):                          # Not quite enough arguments
				errormsg("Missing or invalid USING clause on EXECUTE statement.")
				sqlcode = -99999
				return(False)
			else:
				using = cParms[2].upper()
				if (using != "USING"):                     # Bad syntax again
					errormsg("Missing USING clause on EXECUTE statement.")
					sqlcode = -99999
					return(False)
				
				uSQL = inSQL.upper()
				found = uSQL.find("USING")
				parmString = inSQL[found+5:].strip()
				parmset = splitargs(parmString)
 
				if (len(parmset) == 0):
					errormsg("Missing parameters after the USING clause.")
					sqlcode = -99999
					return(False)
					
				parm_count = 0
				parms = []
				parms.append(None)
				
				CONSTANT = 0
				VARIABLE = 1
				const = [0]
				const_cnt = 0
				
				for v in parmset:
					
					parm_count = parm_count + 1
					parms.append(None)
					
					if (v[1] == True or v[2] == True): # v[1] true if string, v[2] true if num
						
						parm_type = CONSTANT                        
						const_cnt = const_cnt + 1
						if (v[2] == True):
							if (isinstance(v[0],int) == True):         # Integer value 
								sql_type = ibm_db.SQL_INTEGER
							elif (isinstance(v[0],float) == True):       # Float value
								sql_type = ibm_db.SQL_DOUBLE
							else:
								sql_type = ibm_db.SQL_INTEGER
						else:
							sql_type = ibm_db.SQL_CHAR
						
						const.append(v[0])

						
					else:
					
						parm_type = VARIABLE
					
						# See if the variable has a type associated with it varname@type
					
						varset = v[0].split("@")
						parm_name = varset[0]
						
						parm_datatype = "char"

						# Does the variable exist?
						if (parm_name not in globals()):
							errormsg("SQL Execute parameter " + parm_name + " not found")
							sqlcode = -99999
							return(False)       
						
						parms[parm_count] = globals()[parm_name]
		
						if (len(varset) > 1):                # Type provided
							parm_datatype = varset[1]

						if (parm_datatype == "dec" or parm_datatype == "decimal"):
							sql_type = ibm_db.SQL_DOUBLE
						elif (parm_datatype == "bin" or parm_datatype == "binary"):
							sql_type = ibm_db.SQL_BINARY
						elif (parm_datatype == "int" or parm_datatype == "integer"):
							sql_type = ibm_db.SQL_INTEGER
						else:
							sql_type = ibm_db.SQL_CHAR
							parms[parm_count] = addquotes(parms[parm_count],False)
					
					try:
						if (parm_type == VARIABLE):
							result = ibm_db.bind_param(stmt, parm_count, parms[parm_count], ibm_db.SQL_PARAM_INPUT, sql_type)                           
							# result = ibm_db.bind_param(stmt, parm_count, globals()[parm_name], ibm_db.SQL_PARAM_INPUT, sql_type)
						else:
							result = ibm_db.bind_param(stmt, parm_count, const[const_cnt], ibm_db.SQL_PARAM_INPUT, sql_type)
							
					except Exception as e:
						print(repr(e))
						result = False
						
					if (result == False):
						errormsg("SQL Bind on variable " + parm_name + " failed.")
						sqlcode = -99999
						return(False) 
					
				result = ibm_db.execute(stmt) # ,tuple(parms))
				
			if (result == False): 
				errormsg("SQL Execute failed.")      
				return(False)
			
			if (ibm_db.num_fields(stmt) == 0): return(True) # Command successfully completed
						  
			return(fetchResults(stmt))
						
		except Exception as err:
			db2_error(False)
			return(False)
		
		return(False)
  
	return(False)     

def fetchResults(stmt):
	 
	global sqlcode
	
	rows = []
	columns, types = getColumns(stmt)
	
	# By default we assume that the data will be an array
	is_array = True
	
	# Check what type of data we want returned - array or json
	if (flag(["-r","-array"]) == False):
		# See if we want it in JSON format, if not it remains as an array
		if (flag("-json") == True):
			is_array = False
	
	# Set column names to lowercase for JSON records
	if (is_array == False):
		columns = [col.lower() for col in columns] # Convert to lowercase for each of access
	
	# First row of an array has the column names in it
	if (is_array == True):
		rows.append(columns)
		
	result = ibm_db.fetch_tuple(stmt)
	rowcount = 0
	while (result):
		
		rowcount += 1
		
		if (is_array == True):
			row = []
		else:
			row = {}
			
		colcount = 0
		for col in result:
			try:
				if (types[colcount] in ["int","bigint"]):
					if (is_array == True):
						row.append(int(col))
					else:
						row[columns[colcount]] = int(col)
				elif (types[colcount] in ["decimal","real"]):
					if (is_array == True):
						row.append(float(col))
					else:
						row[columns[colcount]] = float(col)
				elif (types[colcount] in ["date","time","timestamp"]):
					if (is_array == True):
						row.append(str(col))
					else:
						row[columns[colcount]] = str(col)
				else:
					if (is_array == True):
						row.append(col)
					else:
						row[columns[colcount]] = col
						
			except:
				if (is_array == True):
					row.append(col)
				else:
					row[columns[colcount]] = col
					
			colcount += 1
		
		rows.append(row)
		result = ibm_db.fetch_tuple(stmt)
		
	if (rowcount == 0): 
		sqlcode = 100        
	else:
		sqlcode = 0
		
	return rows
			

def parseCommit(sql):
	
	global _hdbc, _hdbi, _connected, _stmt, _stmtID, _stmtSQL

	if (_connected == False): return                        # Nothing to do if we are not connected
	
	cParms = sql.split()
	if (len(cParms) == 0): return                           # Nothing to do but this shouldn't happen
	
	keyword = cParms[0].upper()                             # Upper case the keyword
	
	if (keyword == "COMMIT"):                               # Commit the work that was done
		try:
			result = ibm_db.commit (_hdbc)                  # Commit the connection
			if (len(cParms) > 1):
				keyword = cParms[1].upper()
				if (keyword == "HOLD"):
					return
			
			del _stmt[:]
			del _stmtID[:]

		except Exception as err:
			db2_error(False)
		
		return
		
	if (keyword == "ROLLBACK"):                             # Rollback the work that was done
		try:
			result = ibm_db.rollback(_hdbc)                  # Rollback the connection
			del _stmt[:]
			del _stmtID[:]            

		except Exception as err:
			db2_error(False)
		
		return
	
	if (keyword == "AUTOCOMMIT"):                           # Is autocommit on or off
		if (len(cParms) > 1): 
			op = cParms[1].upper()                          # Need ON or OFF value
		else:
			return
		
		try:
			if (op == "OFF"):
				ibm_db.autocommit(_hdbc, False)
			elif (op == "ON"):
				ibm_db.autocommit (_hdbc, True)
			return    
		
		except Exception as err:
			db2_error(False)
			return 
		
	return

def setFlags(inSQL,reset=False):

	global _flags

	if (reset == True):
		_flags = [] # Delete all of the current flag settings

	pos = 0
	end = len(inSQL)-1
	inFlag = False
	ignore = False
	outSQL = ""
	flag = ""

	while (pos <= end):
		ch = inSQL[pos]
		if (ignore == True):   
			outSQL = outSQL + ch
		else:
			if (inFlag == True):
				if (ch != " "):
					flag = flag + ch
				else:
					_flags.append(flag)
					inFlag = False
			else:
				if (ch == "-"):
					flag = "-"
					inFlag = True
				elif (ch == ' '):
					outSQL = outSQL + ch
				else:
					outSQL = outSQL + ch
					ignore = True
		pos += 1

	if (inFlag == True):
		_flags.append(flag)

	return outSQL

def flag(inflag):
	
	global _flags

	if isinstance(inflag,list):
		for x in inflag:
			if (x in _flags):
				return True
		return False
	else:
		if (inflag in _flags):
			return True
		else:
			return False

def execSQL(hdbc,sql,quiet=True):

	success = True
	try:                                                  # See if we have an answer set
		stmt = ibm_db.prepare(hdbc,sql)
		result = ibm_db.execute(stmt)                 # Run it                            
		if (result == False):                         # Error executing the code
			db2_error(quiet)
			success = False
	except:
		db2_error(quiet) 
		success = False

	return success	            

def splitSQL(inputString, delimiter):
	 
	pos = 0
	arg = ""
	results = []
	quoteCH = ""
	
	inSQL = inputString.strip()
	if (len(inSQL) == 0): return(results)       # Not much to do here - no args found
			
	while pos < len(inSQL):
		ch = inSQL[pos]
		pos += 1
		if (ch in ('"',"'")):                   # Is this a quote characters?
			arg = arg + ch                      # Keep appending the characters to the current arg
			if (ch == quoteCH):                 # Is this quote character we are in
				quoteCH = ""
			elif (quoteCH == ""):               # Create the quote
				quoteCH = ch
			else:
				None
		elif (quoteCH != ""):                   # Still in a quote
			arg = arg + ch
		elif (ch == delimiter):                 # Is there a delimiter?
			results.append(arg)
			arg = ""
		else:
			arg = arg + ch
			
	if (arg != ""):
		results.append(arg)
		
	return(results)

def process_slice(connection, dfName, dfValue, pd_dtypes, sql, q, s):
	
	import numpy as np    
	import pandas as pd

	if (q.empty() == False): return None

	if (isinstance(dfValue,list) == True or isinstance(dfValue,tuple) == True):
		encoded_sql = ""
		start = True
		for v in dfValue:
			if (start == False):
				encoded_sql = encoded_sql + ","
			if (isinstance(v,str) == True):
				encoded_sql = encoded_sql + addquotes(v,True)
			else:
				encoded_sql = encoded_sql + str(v)
			start = False

		dfValue = encoded_sql
	elif (isinstance(dfValue,str) == True):
		dfValue = addquotes(dfValue,True)
	else:
		dfValue = str(dfValue)

	if (q.empty() == False): return None

	dsn = (
		   "DRIVER={{IBM DB2 ODBC DRIVER}};"
		   "DATABASE={0};"
		   "HOSTNAME={1};"
		   "PORT={2};"
		   "PROTOCOL=TCPIP;ConnectTimeout=15;"
		   "UID={3};"
		   "PWD={4};{5};{6}").format(_settings.get("database",""), 
								 _settings.get("hostname",""), 
								 _settings.get("port","50000"), 
								 _settings.get("uid",""), 
								 _settings.get("pwd",""),
								 _settings.get("ssl",""),
								 _settings.get("passthru",""))	
	
	# Get a database handle (hdbc) and a statement handle (hstmt) for subsequent access to Db2

	try:
		hdbc  = ibm_db.connect(dsn, "", "")
	except Exception as err:
		try:
			errmsg = ibm_db.conn_errormsg().replace('\r',' ')
			errmsg = errmsg[errmsg.rfind("]")+1:].strip()
		except:
			errmsg = "Error attempting to retrieve error message"
		q.put(errmsg)  
		return None
	
	try:
		hdbi = ibm_db_dbi.Connection(hdbc)
	except Exception as err:
		errmsg = "Connection error when connecting through DBI adapter."
		q.put(errmsg)
		return None

	if (q.empty() == False): return None
	
	# if (isinstance(dfValue,str) == True):
	# 	dfValue = addquotes(dfValue,True)
	# else:
	# 	dfValue = str(dfValue)
		
	protoSQL = sql.replace(f":{dfName}",dfValue)

	s.put(protoSQL)

	if (q.empty() == False): return None	

	try:
		if (pd_dtypes != None):
			df = pd.read_sql_query(protoSQL,hdbi,dtype=pd_dtypes)  
		else:
			df = pd.read_sql_query(protoSQL,hdbi)    
	except:
		try:
			errmsg = ibm_db.stmt_errormsg().replace('\r',' ')
			errmsg = errmsg[errmsg.rfind("]")+1:].strip()		
			ibm_db.close(hdbc)
		except:
			errmsg = "Error attempting to retrieve statement error message."
		q.put(errmsg)
		return None

	if (q.empty() == False): return None

	try:
		ibm_db.close(hdbc)
	except:
		pass	
			  
	return df

def dfSQL(hdbc,hdbi,sqlin,dfName,dfValue,thread_count):
	
	import shlex

	NoDF  = False
	YesDF = True

	sqlin = " ".join(shlex.split(sqlin)) 

	if (hdbc == None or hdbi == None or sqlin in (None, "")):
		return NoDF,None
	
	uSQLin = sqlin.upper()
	  
	select_location = uSQLin.find("SELECT")
	with_location   = uSQLin.find("WITH")

	if (select_location == -1):
		errormsg("SQL statement does not contain a SELECT statement.")
		return NoDF, None          
	  
	if (with_location != -1 and (with_location < select_location)):
		keyword_location = with_location
	else:
		keyword_location = select_location
		
	sql = sqlin[keyword_location:]

	keyword_location = sql.find(f":{dfName}")
	   
	if (keyword_location == -1):
		errormsg(f"The parallelism value ({dfName}) was not found in the SQL statement")
		return NoDF, None
	
	if (isinstance(dfValue,list) == False):
		errormsg(f"The variable {dfName} is not an array or a list of values.")
		return NoDF, None

	#	Create a prototype statement to make sure the SQL will run
	
	protoValue = dfValue[0]

	if (isinstance(protoValue,list) == True or isinstance(protoValue,tuple) == True):
		if (len(protoValue) == 0):
			errormsg(f"The variable {dfName} contains array values that are empty.")
			return NoDF, None				
		protoValue = protoValue[0]

	if (isinstance(protoValue,str) == True):
		protoValue = addquotes(protoValue,True)
	else:
		protoValue = str(protoValue)
		   
	protoSQL = sql.replace(f":{dfName}",protoValue)
	
	try:
		stmt = ibm_db.prepare(hdbc,protoSQL)

		if (ibm_db.num_fields(stmt) == 0):                
			errormsg("The SQL statement does not return an answer set.")
			return NoDF, None
  
	except Exception as err:
		db2_error(False)
		return NoDF, None

	#	Determine the datatypes for a Pandas dataframe if it is supported

	pd_dtypes = None

	if (_pandas_dtype == True):
		pd_dtypes = None
		columns, types = getColumns(stmt)
		pd_dtypes={}
		for idx, col in enumerate(columns):
			try:
				_dindex = _db2types.index(types[idx])
			except:
				_dindex = 0

			pd_dtypes[col] = _pdtypes[_dindex]

		if len(pd_dtypes.keys()) == 0:
			pd_dtypes = None
	
	pool 	 = mp.Pool(processes=thread_count)
	m 		 = multiprocessing.Manager()
	q		 = m.Queue()	
	tracesql = m.Queue()
	
	try:
		results = [pool.apply_async(process_slice, args=(_settings,dfName,x,pd_dtypes,sql,q,tracesql,)) for x in dfValue]
	except Exception as err:
		print(repr(err))
		return NoDF, None        

	output=[]

	badresults = False
	
	for p in results:
		try:
			df = p.get()
			if (isinstance(df,pandas.DataFrame) == True):
				output.append(df)
			else:
				badresults = True
		except Exception as err:
			print(repr(err))
			badresults = True 

	if flag(["-e","-echo"]): 
		while (tracesql.empty() == False):
			debug(tracesql.get(),False)

	if (badresults == True):
		if (q.empty() == False):
			errormsg(q.get())
		return NoDF, None      

	finaldf = pandas.concat(output)
	finaldf.reset_index(drop=True, inplace=True)
	
	if (len(finaldf) == 0):
		sqlcode = 100
		errormsg("No rows found")
		return NoDF, None    

	return YesDF, finaldf

@magics_class
class DB2(Magics):
   
	@needs_local_scope    
	@line_cell_magic
	def sql(self, line, cell=None, local_ns=None):
			
		# Before we event get started, check to see if you have connected yet. Without a connection we 
		# can't do anything. You may have a connection request in the code, so if that is true, we run those,
		# otherwise we connect immediately
		
		# If your statement is not a connect, and you haven't connected, we need to do it for you
	
		global _settings, _environment
		global _hdbc, _hdbi, _connected, sqlstate, sqlerror, sqlcode, sqlelapsed
			 
		# If you use %sql (line) we just run the SQL. If you use %%SQL the entire cell is run.
		
		flag_cell = False
		flag_output = False
		sqlstate = "0"
		sqlerror = ""
		sqlcode = 0
		sqlelapsed = 0
		start_time = time.time()       
		
		# Macros gets expanded before anything is done
		
		SQL1 = line.replace("\n"," ").strip()
		SQL1 = setFlags(SQL1,reset=True)  
		SQL1 = checkMacro(SQL1)                                   # Update the SQL if any macros are in there
		SQL1 = setFlags(SQL1)
		SQL2 = cell    
		
		if SQL1 == "?" or flag(["-h","-help"]):                   # Are you asking for help
			sqlhelp()
			return
		
		if len(SQL1) == 0 and SQL2 == None: return                # Nothing to do here
				
		# Check for help  
		
		sqlType,remainder = sqlParser(SQL1,local_ns)              # What type of command do you have?

		if (sqlType == "CONNECT"):                                # A connect request 
			parseConnect(SQL1,local_ns)
			return 
		elif (sqlType == "USING"):                                # You want to use a dataframe to create a table?
			pdReturn, df = createDF(_hdbc,_hdbi, SQL1,local_ns)
			if (pdReturn == True):
				if flag("-grid") or _settings.get('display',"PANDAS") == 'GRID':   # Check to see if we can display the results
					if (_environment['qgrid'] == False):
						with pandas.option_context('display.max_rows', 100, 'display.max_columns', None):  
							print(df.to_string())
					else:
						try:
							pdisplay(qgrid.show_grid(df))
						except:
							errormsg("Grid cannot be used to display data with duplicate column names. Use option -a or %sql OPTION DISPLAY PANDAS instead.")
					return 
				else:
					if flag(["-a","-all"]) or _settings.get("maxrows",10) == -1 : # All of the rows
						pandas.options.display.max_rows = 100
						pandas.options.display.max_columns = None
						return df # print(df.to_string())
					else:
						pandas.options.display.max_rows = _settings.get("maxrows",10)
						pandas.options.display.max_columns = None
						return df # pdisplay(df) # print(df.to_string())
			else:
				return
		elif (sqlType == "DEFINE"):                               # Create a macro from the body
			result = setMacro(SQL2,remainder)
			return
		elif (sqlType in ("OPTION","OPTIONS")):
			setOptions(SQL1)
			return 
		elif (sqlType == 'COMMIT' or sqlType == 'ROLLBACK' or sqlType == 'AUTOCOMMIT'):
			parseCommit(remainder)
			return
		elif (sqlType == "PREPARE"):
			pstmt = parsePExec(_hdbc, remainder)
			return(pstmt)
		elif (sqlType == "EXECUTE"):
			result = parsePExec(_hdbc, remainder)
			return(result)    
		elif (sqlType == "CALL"):
			result = parseCall(_hdbc, remainder, local_ns)
			return(result)
		else:
			pass        
 
		sql = SQL1
	
		if (sql == ""): sql = SQL2
		
		if (sql == ""): return                                   # Nothing to do here
	
		if (_connected == False):
			if (db2_doConnect() == False):
				errormsg('A CONNECT statement must be issued before issuing SQL statements.')
				return      
		
		if _settings.get("maxrows",10) == -1:                                 # Set the return result size
			pandas.reset_option('display.max_rows')
		else:
			pandas.options.display.max_rows = _settings.get("maxrows",10)
	  
		runSQL = re.sub('.*?--.*$',"",sql,flags=re.M)
		remainder = runSQL.replace("\n"," ") 

		if flag(["-d","-delim"]):
			sqlLines = splitSQL(remainder,"@")
		else:
			sqlLines = splitSQL(remainder,";")
		flag_cell = True
					  
		# For each line figure out if you run it as a command (db2) or select (sql)

		for sqlin in sqlLines:          # Run each command
			
			sqlin = checkMacro(sqlin)                                 # Update based on any macros

			sqlType, sql = sqlParser(sqlin,local_ns)                           # Parse the SQL  
			if (sql.strip() == ""): continue

			if flag(["-e","-echo"]): 
				debug(sql,False)
				
			if flag(["-pb","-bar","-pp","-pie","-pl","-line"]): # We are plotting some results              
				plotData(_hdbi, sql)                            # Plot the data and return
				return                

			try:                                                  # See if we have an answer set
				stmt = ibm_db.prepare(_hdbc,sql)
				if (ibm_db.num_fields(stmt) == 0):                # No, so we just execute the code
					start_time = time.time()
					result = ibm_db.execute(stmt)                 # Run it                            
					sqlelapsed = time.time() - start_time
					if (result == False):                         # Error executing the code
						db2_error(flag(["-q","-quiet"])) 
						continue
						
					rowcount = ibm_db.num_rows(stmt)    
				
					if (rowcount == 0 and flag(["-q","-quiet"]) == False):
						errormsg("No rows found.")     
						
					continue                                      # Continue running
				
				elif flag(["-r","-array","-j","-json"]):                     # raw, json, format json
					row_count = 0
					resultSet = []
					try:
						start_time = time.time()                 
						result = ibm_db.execute(stmt)             # Run it
						sqlelapsed = time.time() - start_time                            
						if (result == False):                         # Error executing the code
							db2_error(flag(["-q","-quiet"]))  
							return
							
						if flag("-j"):                          # JSON single output
							row_count = 0
							json_results = []
							while( ibm_db.fetch_row(stmt) ):
								row_count = row_count + 1
								jsonVal = ibm_db.result(stmt,0)
								jsonDict = json.loads(jsonVal)
								json_results.append(jsonDict)
								flag_output = True                                    
							
							if (row_count == 0): sqlcode = 100
							return(json_results)
						
						else:
							return(fetchResults(stmt))
								
					except Exception as err:
						db2_error(flag(["-q","-quiet"]))
						return
						
				else:

					# New for pandas 1.3. We can coerce the PD datatypes to mimic those of Db2
					
					pd_dtypes = None
					
					if (_pandas_dtype == True):
						pd_dtypes = None
						columns, types = getColumns(stmt)
						pd_dtypes={}
						for idx, col in enumerate(columns):
							try:
								_dindex = _db2types.index(types[idx])
							except:
								_dindex = 0

							pd_dtypes[col] = _pdtypes[_dindex]

						if len(pd_dtypes.keys()) == 0:
							pd_dtypes = None
					try:
						
						start_time = time.time()    
						if (_pandas_dtype == True):
							df = pandas.read_sql_query(sql,_hdbi,dtype=pd_dtypes)  
						else:
							df = pandas.read_sql_query(sql,_hdbi)                        
						sqlelapsed = time.time() - start_time                                
							
					except Exception as err:
						sqlelapsed = 0
						db2_error(False)
						return
												
					if (len(df) == 0):
						sqlcode = 100
						if (flag(["-q","-quiet"]) == False): 
							errormsg("No rows found")
						continue                    
				
					flag_output = True
					if flag("-grid") or _settings.get('display',"PANDAS") == 'GRID':   # Check to see if we can display the results
						if (_environment['qgrid'] == False):
							with pandas.option_context('display.max_rows', None, 'display.max_columns', None):  
								print(df.to_string())
						else:
							try:
								pdisplay(qgrid.show_grid(df))
							except:
								errormsg("Grid cannot be used to display data with duplicate column names. Use option -a or %sql OPTION DISPLAY PANDAS instead.")
								return 
					else:
						if flag(["-a","-all"]) or _settings.get("maxrows",10) == -1 : # All of the rows
							pandas.options.display.max_rows = 100
							pandas.options.display.max_columns = None
							return df # print(df.to_string())
						else:
							pandas.options.display.max_rows = _settings.get("maxrows",10)
							pandas.options.display.max_columns = None
							return df # pdisplay(df) # print(df.to_string())

			except:
				db2_error(flag(["-q","-quiet"]))
				continue # return
				
		sqlelapsed = time.time() - start_time
		if (flag_output == False and flag(["-q","-quiet"]) == False): print("Command completed.")
			
# Register the Magic extension in Jupyter    
ip = get_ipython()          
ip.register_magics(DB2)
load_settings()

macro_list = '''
#
# The LIST macro is used to list all of the tables in the current schema or for all schemas
#
var syntax Syntax: LIST TABLES [FOR ALL | FOR SCHEMA name]
# 
# Only LIST TABLES is supported by this macro
#
flags -a
if {^1} <> 'TABLES'
	exit {syntax}
endif

#
# This SQL is a temporary table that contains the description of the different table types
#
WITH TYPES(TYPE,DESCRIPTION) AS (
  VALUES
	('A','Alias'),
	('G','Created temporary table'),
	('H','Hierarchy table'),
	('L','Detached table'),
	('N','Nickname'),
	('S','Materialized query table'),
	('T','Table'),
	('U','Typed table'),
	('V','View'),
	('W','Typed view')
)
SELECT TABNAME, TABSCHEMA, T.DESCRIPTION FROM SYSCAT.TABLES S, TYPES T
	   WHERE T.TYPE = S.TYPE 

#
# Case 1: No arguments - LIST TABLES
#
if {argc} == 1
   AND OWNER = CURRENT USER
   ORDER BY TABNAME, TABSCHEMA
   return
endif 

#
# Case 2: Need 3 arguments - LIST TABLES FOR ALL
#
if {argc} == 3
	if {^2}&{^3} == 'FOR&ALL'
		ORDER BY TABNAME, TABSCHEMA
		return
	endif
	exit {syntax}
endif

#
# Case 3: Need FOR SCHEMA something here
#
if {argc} == 4
	if {^2}&{^3} == 'FOR&SCHEMA'
		AND TABSCHEMA = '{^4}'
		ORDER BY TABNAME, TABSCHEMA
		return
	else
		exit {syntax}
	endif
endif

#
# Nothing matched - Error
#
exit {syntax}
'''
DB2.sql(None, "define LIST", cell=macro_list, local_ns=locals())

macro_describe = '''
#
# The DESCRIBE command can either use the syntax DESCRIBE TABLE <name> or DESCRIBE TABLE SELECT ...
#
var syntax Syntax: DESCRIBE [TABLE name | SELECT statement] 
#
# Check to see what count of variables is... Must be at least 2 items DESCRIBE TABLE x or SELECT x
#
flags -a
if {argc} < 2
   exit {syntax}
endif

CALL ADMIN_CMD('{*0}');
'''

DB2.sql(None,"define describe", cell=macro_describe, local_ns=locals())

create_sample = """
flags -d
BEGIN
DECLARE FOUND INTEGER;
SET FOUND = (SELECT COUNT(*) FROM SYSIBM.SYSTABLES WHERE NAME='DEPARTMENT' AND CREATOR=CURRENT USER);
IF FOUND = 0 THEN
	EXECUTE IMMEDIATE('CREATE TABLE DEPARTMENT(DEPTNO CHAR(3) NOT NULL, DEPTNAME VARCHAR(36) NOT NULL,
						MGRNO CHAR(6),ADMRDEPT CHAR(3) NOT NULL)');
	EXECUTE IMMEDIATE('INSERT INTO DEPARTMENT VALUES
		(''A00'',''SPIFFY COMPUTER SERVICE DIV.'',''000010'',''A00''),
		(''B01'',''PLANNING'',''000020'',''A00''),
		(''C01'',''INFORMATION CENTER'',''000030'',''A00''),
		(''D01'',''DEVELOPMENT CENTER'',NULL,''A00''),
		(''D11'',''MANUFACTURING SYSTEMS'',''000060'',''D01''),
		(''D21'',''ADMINISTRATION SYSTEMS'',''000070'',''D01''),
		(''E01'',''SUPPORT SERVICES'',''000050'',''A00''),
		(''E11'',''OPERATIONS'',''000090'',''E01''),
		(''E21'',''SOFTWARE SUPPORT'',''000100'',''E01''),
		(''F22'',''BRANCH OFFICE F2'',NULL,''E01''),
		(''G22'',''BRANCH OFFICE G2'',NULL,''E01''),
		(''H22'',''BRANCH OFFICE H2'',NULL,''E01''),
		(''I22'',''BRANCH OFFICE I2'',NULL,''E01''),
		(''J22'',''BRANCH OFFICE J2'',NULL,''E01'')');
END IF;

SET FOUND = (SELECT COUNT(*) FROM SYSIBM.SYSTABLES WHERE NAME='EMPLOYEE' AND CREATOR=CURRENT USER);
IF FOUND = 0 THEN
	EXECUTE IMMEDIATE('CREATE TABLE EMPLOYEE(
						EMPNO CHAR(6) NOT NULL,
						FIRSTNME VARCHAR(12) NOT NULL,
						MIDINIT CHAR(1),
						LASTNAME VARCHAR(15) NOT NULL,
						WORKDEPT CHAR(3),
						PHONENO CHAR(4),
						HIREDATE DATE,
						JOB CHAR(8),
						EDLEVEL SMALLINT NOT NULL,
						SEX CHAR(1),
						BIRTHDATE DATE,
						SALARY DECIMAL(9,2),
						BONUS DECIMAL(9,2),
						COMM DECIMAL(9,2)
						)');
	EXECUTE IMMEDIATE('INSERT INTO EMPLOYEE VALUES
		(''000010'',''CHRISTINE'',''I'',''HAAS''      ,''A00'',''3978'',''1995-01-01'',''PRES    '',18,''F'',''1963-08-24'',152750.00,1000.00,4220.00),
		(''000020'',''MICHAEL''  ,''L'',''THOMPSON''  ,''B01'',''3476'',''2003-10-10'',''MANAGER '',18,''M'',''1978-02-02'',94250.00,800.00,3300.00),
		(''000030'',''SALLY''    ,''A'',''KWAN''      ,''C01'',''4738'',''2005-04-05'',''MANAGER '',20,''F'',''1971-05-11'',98250.00,800.00,3060.00),
		(''000050'',''JOHN''     ,''B'',''GEYER''     ,''E01'',''6789'',''1979-08-17'',''MANAGER '',16,''M'',''1955-09-15'',80175.00,800.00,3214.00),
		(''000060'',''IRVING''   ,''F'',''STERN''     ,''D11'',''6423'',''2003-09-14'',''MANAGER '',16,''M'',''1975-07-07'',72250.00,500.00,2580.00),
		(''000070'',''EVA''      ,''D'',''PULASKI''   ,''D21'',''7831'',''2005-09-30'',''MANAGER '',16,''F'',''2003-05-26'',96170.00,700.00,2893.00),
		(''000090'',''EILEEN''   ,''W'',''HENDERSON'' ,''E11'',''5498'',''2000-08-15'',''MANAGER '',16,''F'',''1971-05-15'',89750.00,600.00,2380.00),
		(''000100'',''THEODORE'' ,''Q'',''SPENSER''   ,''E21'',''0972'',''2000-06-19'',''MANAGER '',14,''M'',''1980-12-18'',86150.00,500.00,2092.00),
		(''000110'',''VINCENZO'' ,''G'',''LUCCHESSI'' ,''A00'',''3490'',''1988-05-16'',''SALESREP'',19,''M'',''1959-11-05'',66500.00,900.00,3720.00),
		(''000120'',''SEAN''     ,'' '',''O`CONNELL'' ,''A00'',''2167'',''1993-12-05'',''CLERK   '',14,''M'',''1972-10-18'',49250.00,600.00,2340.00),
		(''000130'',''DELORES''  ,''M'',''QUINTANA''  ,''C01'',''4578'',''2001-07-28'',''ANALYST '',16,''F'',''1955-09-15'',73800.00,500.00,1904.00),
		(''000140'',''HEATHER''  ,''A'',''NICHOLLS''  ,''C01'',''1793'',''2006-12-15'',''ANALYST '',18,''F'',''1976-01-19'',68420.00,600.00,2274.00),
		(''000150'',''BRUCE''    ,'' '',''ADAMSON''   ,''D11'',''4510'',''2002-02-12'',''DESIGNER'',16,''M'',''1977-05-17'',55280.00,500.00,2022.00),
		(''000160'',''ELIZABETH'',''R'',''PIANKA''    ,''D11'',''3782'',''2006-10-11'',''DESIGNER'',17,''F'',''1980-04-12'',62250.00,400.00,1780.00),
		(''000170'',''MASATOSHI'',''J'',''YOSHIMURA'' ,''D11'',''2890'',''1999-09-15'',''DESIGNER'',16,''M'',''1981-01-05'',44680.00,500.00,1974.00),
		(''000180'',''MARILYN''  ,''S'',''SCOUTTEN''  ,''D11'',''1682'',''2003-07-07'',''DESIGNER'',17,''F'',''1979-02-21'',51340.00,500.00,1707.00),
		(''000190'',''JAMES''    ,''H'',''WALKER''    ,''D11'',''2986'',''2004-07-26'',''DESIGNER'',16,''M'',''1982-06-25'',50450.00,400.00,1636.00),
		(''000200'',''DAVID''    ,'' '',''BROWN''     ,''D11'',''4501'',''2002-03-03'',''DESIGNER'',16,''M'',''1971-05-29'',57740.00,600.00,2217.00),
		(''000210'',''WILLIAM''  ,''T'',''JONES''     ,''D11'',''0942'',''1998-04-11'',''DESIGNER'',17,''M'',''2003-02-23'',68270.00,400.00,1462.00),
		(''000220'',''JENNIFER'' ,''K'',''LUTZ''      ,''D11'',''0672'',''1998-08-29'',''DESIGNER'',18,''F'',''1978-03-19'',49840.00,600.00,2387.00),
		(''000230'',''JAMES''    ,''J'',''JEFFERSON'' ,''D21'',''2094'',''1996-11-21'',''CLERK   '',14,''M'',''1980-05-30'',42180.00,400.00,1774.00),
		(''000240'',''SALVATORE'',''M'',''MARINO''    ,''D21'',''3780'',''2004-12-05'',''CLERK   '',17,''M'',''2002-03-31'',48760.00,600.00,2301.00),
		(''000250'',''DANIEL''   ,''S'',''SMITH''     ,''D21'',''0961'',''1999-10-30'',''CLERK   '',15,''M'',''1969-11-12'',49180.00,400.00,1534.00),
		(''000260'',''SYBIL''    ,''P'',''JOHNSON''   ,''D21'',''8953'',''2005-09-11'',''CLERK   '',16,''F'',''1976-10-05'',47250.00,300.00,1380.00),
		(''000270'',''MARIA''    ,''L'',''PEREZ''     ,''D21'',''9001'',''2006-09-30'',''CLERK   '',15,''F'',''2003-05-26'',37380.00,500.00,2190.00),
		(''000280'',''ETHEL''    ,''R'',''SCHNEIDER'' ,''E11'',''8997'',''1997-03-24'',''OPERATOR'',17,''F'',''1976-03-28'',36250.00,500.00,2100.00),
		(''000290'',''JOHN''     ,''R'',''PARKER''    ,''E11'',''4502'',''2006-05-30'',''OPERATOR'',12,''M'',''1985-07-09'',35340.00,300.00,1227.00),
		(''000300'',''PHILIP''   ,''X'',''SMITH''     ,''E11'',''2095'',''2002-06-19'',''OPERATOR'',14,''M'',''1976-10-27'',37750.00,400.00,1420.00),
		(''000310'',''MAUDE''    ,''F'',''SETRIGHT''  ,''E11'',''3332'',''1994-09-12'',''OPERATOR'',12,''F'',''1961-04-21'',35900.00,300.00,1272.00),
		(''000320'',''RAMLAL''   ,''V'',''MEHTA''     ,''E21'',''9990'',''1995-07-07'',''FIELDREP'',16,''M'',''1962-08-11'',39950.00,400.00,1596.00),
		(''000330'',''WING''     ,'' '',''LEE''       ,''E21'',''2103'',''2006-02-23'',''FIELDREP'',14,''M'',''1971-07-18'',45370.00,500.00,2030.00),
		(''000340'',''JASON''    ,''R'',''GOUNOT''    ,''E21'',''5698'',''1977-05-05'',''FIELDREP'',16,''M'',''1956-05-17'',43840.00,500.00,1907.00),
		(''200010'',''DIAN''     ,''J'',''HEMMINGER'' ,''A00'',''3978'',''1995-01-01'',''SALESREP'',18,''F'',''1973-08-14'',46500.00,1000.00,4220.00),
		(''200120'',''GREG''     ,'' '',''ORLANDO''   ,''A00'',''2167'',''2002-05-05'',''CLERK   '',14,''M'',''1972-10-18'',39250.00,600.00,2340.00),
		(''200140'',''KIM''      ,''N'',''NATZ''      ,''C01'',''1793'',''2006-12-15'',''ANALYST '',18,''F'',''1976-01-19'',68420.00,600.00,2274.00),
		(''200170'',''KIYOSHI''  ,'' '',''YAMAMOTO''  ,''D11'',''2890'',''2005-09-15'',''DESIGNER'',16,''M'',''1981-01-05'',64680.00,500.00,1974.00),
		(''200220'',''REBA''     ,''K'',''JOHN''      ,''D11'',''0672'',''2005-08-29'',''DESIGNER'',18,''F'',''1978-03-19'',69840.00,600.00,2387.00),
		(''200240'',''ROBERT''   ,''M'',''MONTEVERDE'',''D21'',''3780'',''2004-12-05'',''CLERK   '',17,''M'',''1984-03-31'',37760.00,600.00,2301.00),
		(''200280'',''EILEEN''   ,''R'',''SCHWARTZ''  ,''E11'',''8997'',''1997-03-24'',''OPERATOR'',17,''F'',''1966-03-28'',46250.00,500.00,2100.00),
		(''200310'',''MICHELLE'' ,''F'',''SPRINGER''  ,''E11'',''3332'',''1994-09-12'',''OPERATOR'',12,''F'',''1961-04-21'',35900.00,300.00,1272.00),
		(''200330'',''HELENA''   ,'' '',''WONG''      ,''E21'',''2103'',''2006-02-23'',''FIELDREP'',14,''F'',''1971-07-18'',35370.00,500.00,2030.00),
		(''200340'',''ROY''      ,''R'',''ALONZO''    ,''E21'',''5698'',''1997-07-05'',''FIELDREP'',16,''M'',''1956-05-17'',31840.00,500.00,1907.00)');                             
END IF;
END"""

DB2.sql(None,"define sampledata", cell=create_sample, local_ns=locals())

create_set = '''
#
# Convert a SET statement into an OPTION statement
#

# Display settings
if {^1} == 'DISPLAY'
	if {^2} == "PANDAS" 
		OPTION DISPLAY PANDAS
		return
	else
		if {^2} == "GRID"
			OPTION DISPLAY GRID
			return
		endif
	endif
endif

# Multithreading
if {^1} == 'THREADS'
	OPTION THREADS {2}
	return
endif
		
# Maximum number of rows displayed
if {^1} == 'MAXROWS'
	OPTION MAXROWS {2}
	return
endif

# Maximum number of grid rows displayed
if {^1} == 'MAXGRID'
	OPTION MAXGRID {2}
	return
endif
		
{*0}
return
'''

DB2.sql(None,"define set", cell=create_set, local_ns=locals())
   
success("Db2 Extensions Loaded.")
