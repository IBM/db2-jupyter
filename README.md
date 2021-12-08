# Db2 Magic Command for Jupyter Notebooks

Jupyter notebooks include the ability to extend the syntax available within code blocks with a feature called [Magic](https://ipython.readthedocs.io/en/stable/interactive/magics.html) commands. Magic commands start with a percent sign `%` and provide a variety of features within a notebook environment, including modifying notebook behavior, executing OS commands, extending notebook functionality and with Db2 magic, a way of interacting with a Db2 database.

Once you have loaded the Db2 magic commands into your notebook, you are able to query Db2 tables using standard SQL syntax:

![Intro Sample](docs/img/intro_sample.png)

Db2 magic commands provide a number of features that will simplify your use of Db2 databases, including:

- Simplified connections to data sources
- Ability to store result sets into Pandas dataframes
- Create Db2 tables from Pandas dataframes and populate the tables with the data frame contents
- Run the majority of DCL, DDL, and DML statements that are available in Db2
- Create functions, stored procedures, and run a subset of administrative commands
- Allow for parallel execution of SQL queries even on non-warehousing systems
- And much more!

## Pre-requisites

If you are running on a Jupyter notebook service (Watson Studio), you may already have some of these pre-requisites installed. You can check to see if the Db2 libraries are installed by running the following command in a Jupyter notebook code cell:
```
import ibm_db
```

If the command returns sucessfully, then you do not need to install `ibm_db` and can continue to the *Loading Db2 Magic Commands* section.

If you have access to your Jupyter notebook environment, the Db2 Python client can be installed in one of three ways:

- `python3 -m pip install ibm_db` or `pip install ibm_db`
- `easy_install ibm_db`
- `conda install ibm_db` 

Prior to running the installation you may want to run these commands to ensure the proper libraries are available for the Db2 drivers:

- RHEL/CentOS `yum install python3-dev`
- Ubuntu `apt-get install python3-dev`

More detailed instructions can be found on the [Db2 Python Driver](https://github.com/ibmdb/python-ibmdb#inst) support page.

## Loading Db2 Magic Commands

Once you have `ibm_db` installed, you will need to download the Db2 magic commands. The Db2 magic commands can be downloaded and placed directly to the directory that your Jupyter notebooks are stored in, or can be downloaded from within a Jupyter notebook.

To load the Db2 magic commands into your notebook, run the following command in your Jupyter notebook:
```
!wget https://raw.githubusercontent.com/IBM/db2-jupyter/master/db2.ipynb
```

Once you have loaded the Db2 magic commands into your notebook, you are able to query Db2 tables using standard SQL syntax:
```
%run db2.ipynb
%sql connect to sample
%sql select * from employee
```

## Db2 Magic Commands Help

For more information on the Db2 Magic commands, refer the online [Db2 Magic Commands](https://github.com/IBM/db2-jupyter) documentation.

# Support

For any questions regarding the Db2 Magic commands, including any suggestions, general comments, or bug reports, please contact:

* George Baklarz `baklarz@ca.ibm.com`
* Phil Downey `phil.downey1@ibm.com`

George & Phil

### Acknowledgements

We would like to thank the following people who helped in early prototying, testing, suggestions, and feedback on the Db2 Magic commands.

* Peter Kohlmann
* Dean Compher